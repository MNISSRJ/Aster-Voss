"""Aster Voss interactive CLI."""
from __future__ import annotations
import sys
import log
from agent import AsterVoss
from aster import AGENT_IDENTITY,AGENT_TAGLINE,PROJECT_VERSION,get_memory
from config import load_config
from llm.base import LLMError
from llm.factory import available_providers,create_provider
from memory.persistence import memory_stats
def build_system_prompt():
    sections=[AGENT_IDENTITY.render_system_prompt()]
    m=get_memory().context_block()
    if m:sections.append(m)
    return "\n\n".join(sections)
def main():
    config=load_config();log.configure(config.log_level)
    agent=AsterVoss(config,system_prompt=build_system_prompt(),identity_name=AGENT_IDENTITY.name,identity_tagline=AGENT_TAGLINE)
    print(f"{AGENT_IDENTITY.name} v{PROJECT_VERSION} - {AGENT_TAGLINE}")
    print(f"Memory = persistent ({memory_stats()['history_messages']} history messages)")
    while True:
        try:user_input=input("you > ").strip()
        except (EOFError,KeyboardInterrupt):print();return 0
        if not user_input:continue
        if user_input in {"/exit","/quit"}:return 0
        if user_input=="/reset":agent.reset();print("(history cleared)");continue
        if user_input=="/status":
            print(agent.display_name,config.main_provider,available_providers(config));continue
        if user_input=="/identity":print(AGENT_IDENTITY.render_system_prompt());continue
        print("\n"+agent.run(user_input).text+"\n")
if __name__=="__main__":sys.exit(main())
