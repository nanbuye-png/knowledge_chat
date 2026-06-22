import { create } from 'zustand'
import type { Document, DocumentState } from '../types'
import * as documentsApi from '../api/documents'

export const useDocumentStore = create<DocumentState>((set) => ({
  documents: [],
  loading: false,

  fetchDocuments: async () => {
    set({ loading: true })
    try {
      const docs = await documentsApi.fetchDocuments()
      set({ documents: docs, loading: false })
    } catch (error) {
      console.error('Failed to fetch documents:', error)
      set({ loading: false })
    }
  },

  addDocument: (doc: Document) =>
    set((state) => ({
      documents: [doc, ...state.documents],
    })),

  removeDocument: (id: string) =>
    set((state) => ({
      documents: state.documents.filter((d) => d.id !== id),
    })),

  updateDocumentStatus: (id: string, status: Document['status'], chunk_count?: number) =>
    set((state) => ({
      documents: state.documents.map((d) =>
        d.id === id ? { ...d, status, chunk_count: chunk_count ?? d.chunk_count } : d
      ),
    })),
}))