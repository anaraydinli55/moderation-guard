# { "Depends": "py-genlayer:test" }
from genlayer import *

class TestContract(gl.Contract):
    def __init__(self):
        pass
    
    @gl.public.view
    def hello(self):
        return "hello"
