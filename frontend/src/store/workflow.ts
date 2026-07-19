import { create } from 'zustand'
import type { Workflow } from '../api/workflows'

interface WorkflowState {
  selectedWorkflow: Workflow | null
  workflows: Workflow[]
  setSelectedWorkflow: (w: Workflow | null) => void
  setWorkflows: (workflows: Workflow[]) => void
}

export const useWorkflowStore = create<WorkflowState>((set) => ({
  selectedWorkflow: null,
  workflows: [],
  setSelectedWorkflow: (w) => set({ selectedWorkflow: w }),
  setWorkflows: (workflows) => set({ workflows }),
}))