import { create } from 'zustand'

interface AppStore {
  selectedTraceIds: string[]
  selectedScorers: string[]
  draftEvalConfig: any
  selectedReports: string[]

  setSelectedTraceIds: (ids: string[]) => void
  setSelectedScorers: (ids: string[]) => void
  toggleTrace: (id: string) => void
  toggleScorer: (id: string) => void

  setDraftEvalConfig: (config: any) => void
  clearDraftEvalConfig: () => void

  setSelectedReports: (ids: string[]) => void
  toggleReport: (id: string) => void
}

export const useAppStore = create<AppStore>((set) => ({
  selectedTraceIds: [],
  selectedScorers: [],
  draftEvalConfig: null,
  selectedReports: [],

  setSelectedTraceIds: (ids) => set({ selectedTraceIds: ids }),
  setSelectedScorers: (ids) => set({ selectedScorers: ids }),
  toggleTrace: (id) => set((s) => ({
    selectedTraceIds: s.selectedTraceIds.includes(id)
      ? s.selectedTraceIds.filter((x) => x !== id)
      : [...s.selectedTraceIds, id],
  })),
  toggleScorer: (id) => set((s) => ({
    selectedScorers: s.selectedScorers.includes(id)
      ? s.selectedScorers.filter((x) => x !== id)
      : [...s.selectedScorers, id],
  })),

  setDraftEvalConfig: (config) => set({ draftEvalConfig: config }),
  clearDraftEvalConfig: () => set({ draftEvalConfig: null }),

  setSelectedReports: (ids) => set({ selectedReports: ids }),
  toggleReport: (id) => set((s) => ({
    selectedReports: s.selectedReports.includes(id)
      ? s.selectedReports.filter((x) => x !== id)
      : [...s.selectedReports, id],
  })),
}))
