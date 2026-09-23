class NullJev:
    enabled=False
    def decide(self,*args,**kwargs): return None
def create_jev_client(config): return NullJev()
