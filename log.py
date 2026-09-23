import logging
def configure(level="INFO"): logging.basicConfig(level=getattr(logging,level.upper(),logging.INFO),format="%(levelname)s %(message)s")
def error(msg,*args): logging.getLogger("aster").error(msg,*args)
def info(msg,*args): logging.getLogger("aster").info(msg,*args)
