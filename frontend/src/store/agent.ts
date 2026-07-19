import { create } from 'zustand'
import type { Agent } from '../api/agents'

interface AgentState {
  selectedAgent: Agent | null
  agents: Agent[]
  setSelectedAgent: (a: Agent | null) => void
  setAgents: (agents: Agent[]) => void
}

export const useAgentStore = create<AgentState>((set) => ({
  selectedAgent: null,
  agents: [],
  setSelectedAgent: (a) => set({ selectedAgent: a }),
  setAgents: (agents) => set({ agents }),
}))