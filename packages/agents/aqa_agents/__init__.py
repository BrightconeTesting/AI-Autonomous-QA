"""Five core AI agents — LangGraph-ready stubs (Day 8)."""

from aqa_agents.discovery import DiscoveryAgent, DiscoveryInput, DiscoveryOutput
from aqa_agents.healing import HealingAgent, HealingInput, HealingOutput
from aqa_agents.intelligence import IntelligenceAgent, IntelligenceInput, IntelligenceOutput
from aqa_agents.script_generation import (
    ScriptGenerationAgent,
    ScriptGenerationInput,
    ScriptGenerationOutput,
)
from aqa_agents.test_design import TestDesignAgent, TestDesignInput, TestDesignOutput

__all__ = [
    "DiscoveryAgent",
    "DiscoveryInput",
    "DiscoveryOutput",
    "TestDesignAgent",
    "TestDesignInput",
    "TestDesignOutput",
    "ScriptGenerationAgent",
    "ScriptGenerationInput",
    "ScriptGenerationOutput",
    "IntelligenceAgent",
    "IntelligenceInput",
    "IntelligenceOutput",
    "HealingAgent",
    "HealingInput",
    "HealingOutput",
    "ALL_AGENTS",
]

ALL_AGENTS = (
    DiscoveryAgent,
    TestDesignAgent,
    ScriptGenerationAgent,
    IntelligenceAgent,
    HealingAgent,
)
