from memory.service import MemoryService
from services.conversation_service import ConversationService
from services.radar_service import RadarService

def test_services_have_explicit_boundaries():
    assert hasattr(MemoryService, "context")
    assert hasattr(ConversationService, "save")
    assert hasattr(RadarService, "generate")
