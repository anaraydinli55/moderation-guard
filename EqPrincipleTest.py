# { "Depends": "py-genlayer:test" }
import genlayer as gl

class EqPrincipleTest(gl.contract.Contract):
    def __init__(self):
        super().__init__()  # ✅ Method register'ı için gerekli
    
    @gl.public.write
    def testConsensus(self, prompt):
        result = gl.nondet.exec_prompt(str(prompt))
        return str(result)
