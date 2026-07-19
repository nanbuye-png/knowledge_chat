import { create } from 'zustand'
import type { LLMModel } from '../api/models'

interface ModelState {
  selectedModel: LLMModel | null
  models: LLMModel[]
  setSelectedModel: (model: LLMModel) => void
  setModels: (models: LLMModel[]) => void
}

export const useModelStore = create<ModelState>((set) => ({
  selectedModel: null,
  models: [],
  setSelectedModel: (model) => set({ selectedModel: model }),
  setModels: (models) => set({ models }),
}))