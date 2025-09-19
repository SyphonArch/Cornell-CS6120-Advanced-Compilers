from abc import ABC, abstractmethod
from collections import deque
from typing import List, Dict, Tuple, Optional, Self
from enum import Enum


class DataFlowFact(ABC):
    @abstractmethod
    def merge(self, other: Self) -> Self:
        pass

    @abstractmethod
    def transfer(self, instr: dict) -> Self:
        pass

    @abstractmethod
    def __eq__(self, other: object) -> bool:
        pass

    @classmethod
    @abstractmethod
    def top(cls) -> Self:
        pass

    @classmethod
    @abstractmethod
    def bottom(cls) -> Self:
        pass


class Direction(Enum):
    FORWARD = 1
    BACKWARD = 2


class Seed(Enum):
    KEEP = 0
    TOP = 1
    BOTTOM = 2


class DFA:
    def __init__(self, cfg: dict, direction: Direction, fact_cls: type[DataFlowFact],
                 entry: Seed = Seed.KEEP, exit: Seed = Seed.KEEP):
        self.cfg = cfg
        self.direction = direction
        self.fact_cls = fact_cls
        self.entry_seed = entry
        self.exit_seed = exit

        self.in_lattice: List[DataFlowFact] = [fact_cls.top() for _ in cfg["blocks"]]
        self.out_lattice: List[DataFlowFact] = [fact_cls.top() for _ in cfg["blocks"]]

        self.inst_in_lattice: Dict[int, List[DataFlowFact]] = {}
        self.inst_out_lattice: Dict[int, List[DataFlowFact]] = {}

        self.block_names: List[str] = [b["name"] for b in cfg["blocks"]]
        self.name2idx: Dict[str, int] = {n: i for i, n in enumerate(self.block_names)}

        edges_by_name: Dict[str, List[str]] = cfg["cfg"].get("edges", {})
        n = len(self.block_names)
        self.succ: List[List[int]] = [[] for _ in range(n)]
        self.pred: List[List[int]] = [[] for _ in range(n)]
        for s_name, dst_names in edges_by_name.items():
            if s_name not in self.name2idx:
                continue
            s = self.name2idx[s_name]
            for d_name in dst_names:
                if d_name not in self.name2idx:
                    continue
                d = self.name2idx[d_name]
                self.succ[s].append(d)
                self.pred[d].append(s)

        self._solved: bool = False

    def _apply_seed(self, seed: Seed, idxs: List[int], target: List[DataFlowFact]):
        if seed is Seed.KEEP:
            return
        if seed is Seed.TOP:
            val = self.fact_cls.top()
        elif seed is Seed.BOTTOM:
            val = self.fact_cls.bottom()
        else:
            raise ValueError("Unknown seed")
        for i in idxs:
            target[i] = val

    def _seed_boundaries(self, work_in: List[DataFlowFact], work_out: List[DataFlowFact]):
        if self.direction is Direction.FORWARD and self.entry_seed is not Seed.KEEP:
            entry_name = self.cfg["cfg"].get("entry")
            if entry_name in self.name2idx:
                self._apply_seed(self.entry_seed, [self.name2idx[entry_name]], work_in)

        if self.direction is Direction.BACKWARD and self.exit_seed is not Seed.KEEP:
            exit_names = self.cfg["cfg"].get("exits")
            if not exit_names:
                exit_names = [self.block_names[i] for i, s in enumerate(self.succ) if not s]
            idxs = [self.name2idx[n] for n in exit_names if n in self.name2idx]
            self._apply_seed(self.exit_seed, idxs, work_out)

    def run(self):
        if self._solved:
            return self.in_lattice, self.out_lattice

        n = len(self.block_names)
        if n == 0:
            self._solved = True
            return self.in_lattice, self.out_lattice

        def meet_many(vals: List[DataFlowFact]) -> DataFlowFact:
            acc = self.fact_cls.top()
            for v in vals:
                acc = acc.merge(v)
            return acc

        work_in = list(self.in_lattice)
        work_out = list(self.out_lattice)
        self._seed_boundaries(work_in, work_out)

        work = deque(range(n))
        while work:
            b = work.popleft()
            instrs = self.cfg["blocks"][b]["instrs"]

            if self.direction is Direction.FORWARD:
                new_in = meet_many([work_out[p] for p in self.pred[b]]) if self.pred[b] else work_in[b]
                cur = new_in
                inst_in: List[DataFlowFact] = []
                inst_out: List[DataFlowFact] = []
                for ins in instrs:
                    inst_in.append(cur)
                    cur = cur.transfer(ins)
                    inst_out.append(cur)
                new_out = cur
            else:
                new_out = meet_many([work_in[s] for s in self.succ[b]]) if self.succ[b] else work_out[b]
                cur = new_out
                inst_in_rev: List[DataFlowFact] = []
                inst_out_rev: List[DataFlowFact] = []
                for ins in reversed(instrs):
                    inst_out_rev.append(cur)
                    cur = cur.transfer(ins)
                    inst_in_rev.append(cur)
                new_in = cur
                inst_in = list(reversed(inst_in_rev))
                inst_out = list(reversed(inst_out_rev))

            changed = (new_in != work_in[b]) or (new_out != work_out[b])
            self.inst_in_lattice[b] = inst_in
            self.inst_out_lattice[b] = inst_out

            if changed:
                work_in[b], work_out[b] = new_in, new_out
                neighbors = self.succ[b] if self.direction is Direction.FORWARD else self.pred[b]
                for nb in neighbors:
                    work.append(nb)

        self.in_lattice = work_in
        self.out_lattice = work_out
        self._solved = True
        return self.in_lattice, self.out_lattice
