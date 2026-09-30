# { "Depends": "py-genlayer:test" }
from genlayer import *

class NondetTest(gl.Contract):
    @gl.public.view
    def testPrompt(self):
        result = gl.nondet.exec_prompt("Say hello in one word")
        return str(result)
