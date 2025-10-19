#include "llvm/IR/IRBuilder.h"
#include "llvm/IR/InstrTypes.h"
#include "llvm/IR/Instructions.h"
#include "llvm/IR/Module.h"
#include "llvm/IR/PassManager.h"
#include "llvm/IR/Type.h"
#include "llvm/IR/Intrinsics.h"
#include "llvm/Passes/PassBuilder.h"
#include "llvm/Passes/PassPlugin.h"
#include "llvm/Support/raw_ostream.h"

using namespace llvm;

namespace {

struct IntTropicalSemiringPass : public PassInfoMixin<IntTropicalSemiringPass> {
  PreservedAnalyses run(Function &function, FunctionAnalysisManager &AM) {
    SmallVector<Instruction *, 16> instructionsToErase;

    for (auto &basicBlock : function) {
      for (auto &instruction : basicBlock) {
        auto *binaryOperator = dyn_cast<BinaryOperator>(&instruction);
        if (!binaryOperator)
          continue;

        unsigned opcode = binaryOperator->getOpcode();
        Value *leftOperand = binaryOperator->getOperand(0);
        Value *rightOperand = binaryOperator->getOperand(1);

        Type *resultType = binaryOperator->getType();
        if (!resultType->isIntegerTy())
          continue; // Only rewrite integer operations

        IRBuilder<> builder(binaryOperator);

        if (opcode == Instruction::Add) {
          // Heuristic: don't rewrite loop-induction updates like `i = i + 1`.
          // We identify these by checking for constant integer operands equal to 1.
          if (auto *constInt = dyn_cast<ConstantInt>(rightOperand)) {
            if (constInt->isOne()) {
              continue; // Skip rewriting this addition
            }
          } else if (auto *constInt = dyn_cast<ConstantInt>(leftOperand)) {
            if (constInt->isOne()) {
              continue; // Skip rewriting this addition
            }
          }
          // Replace addition with smax intrinsic
          Module *module = function.getParent();
          Function *sMaxIntrinsic = Intrinsic::getOrInsertDeclaration(module, Intrinsic::smax, {resultType});
          CallInst *newValue = builder.CreateCall(sMaxIntrinsic, {leftOperand, rightOperand}, binaryOperator->getName());
          binaryOperator->replaceAllUsesWith(newValue);
          instructionsToErase.push_back(binaryOperator); // Mark for deletion
        } else if (opcode == Instruction::Mul) {
          // Replace multiplication with addition
          Value *newValue = builder.CreateAdd(leftOperand, rightOperand, binaryOperator->getName());
          binaryOperator->replaceAllUsesWith(newValue);
          instructionsToErase.push_back(binaryOperator); // Mark for deletion
        }
      }
    }

    for (Instruction *inst : instructionsToErase) {
      inst->eraseFromParent();
    }

    // No analysis is preserved since we modified the function
    return instructionsToErase.empty() ? PreservedAnalyses::all() : PreservedAnalyses::none();
  }
};

}

extern "C" LLVM_ATTRIBUTE_WEAK ::llvm::PassPluginLibraryInfo
llvmGetPassPluginInfo() {
  return {
      .APIVersion = LLVM_PLUGIN_API_VERSION,
      .PluginName = "IntTropicalSemiring",
      .PluginVersion = "v0.1",
      .RegisterPassBuilderCallbacks = [](PassBuilder &PB) {
        PB.registerPipelineStartEPCallback(
            [](ModulePassManager &MPM, OptimizationLevel Level) {
              MPM.addPass(createModuleToFunctionPassAdaptor(IntTropicalSemiringPass()));
            });
      }};
}
