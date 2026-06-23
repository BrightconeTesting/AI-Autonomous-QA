export type DiscoverPersona = {
  personaId: string;
  label: string;
};

export type LlmBudgets = {
  flowStructure: number;
  moduleStructure: number;
  entities: number;
  testAreas: number;
  totalCap: number;
};

export type DiscoverSettings = {
  useLlm: boolean;
  captureNetwork: boolean;
  captureHar: boolean;
  openapiUrl: string;
  llmBudgets: LlmBudgets;
  personas: DiscoverPersona[];
};

export const LLM_BUDGET_DEFAULTS: LlmBudgets = {
  flowStructure: 3000,
  moduleStructure: 2500,
  entities: 2000,
  testAreas: 2000,
  totalCap: 8000,
};

export function defaultDiscoverSettings(): DiscoverSettings {
  return {
    useLlm: true,
    captureNetwork: true,
    captureHar: false,
    openapiUrl: "",
    llmBudgets: { ...LLM_BUDGET_DEFAULTS },
    personas: [],
  };
}

export function toDiscoverConfigPayload(settings: DiscoverSettings): Record<string, unknown> {
  const payload: Record<string, unknown> = {
    use_llm: settings.useLlm,
    captureNetwork: settings.captureNetwork,
    captureHar: settings.captureHar,
    llmBudgets: {
      flow_structure: settings.llmBudgets.flowStructure,
      module_structure: settings.llmBudgets.moduleStructure,
      entities: settings.llmBudgets.entities,
      test_areas: settings.llmBudgets.testAreas,
      totalCap: settings.llmBudgets.totalCap,
    },
    personas: settings.personas.map((p) => ({
      personaId: p.personaId,
      label: p.label || p.personaId,
    })),
  };
  if (settings.openapiUrl.trim()) {
    payload.openapiUrl = settings.openapiUrl.trim();
  }
  return payload;
}
