import { useState, useEffect, useCallback } from 'react'
import * as adminApi from '../api/admin'
import type { DashboardData, SystemMonitorStatus } from '../api/admin'

interface UseDashboardOptions {
  refreshInterval?: number
  autoRefresh?: boolean
}

interface UseDashboardReturn {
  dashboard: DashboardData | null
  /** @deprecated Use dashboard instead */
  overview: any | null
  system: SystemMonitorStatus | null
  loading: boolean
  error: string | null
  refresh: () => Promise<void>
}

export function useDashboard(options: UseDashboardOptions = {}): UseDashboardReturn {
  const { refreshInterval = 30000, autoRefresh = true } = options

  const [dashboard, setDashboard] = useState<DashboardData | null>(null)
  /** @deprecated overview is kept for backward compatibility */
  const [overview, setOverview] = useState<any | null>(null)
  const [system, setSystem] = useState<SystemMonitorStatus | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  const fetchData = useCallback(async () => {
    try {
      setError(null)
      const [dashboardData, overviewData, systemData] = await Promise.all([
        adminApi.getDashboard(),
        adminApi.getDashboardOverview().catch(() => null),
        adminApi.getSystemMonitorStatus(),
      ])
      setDashboard(dashboardData)
      setOverview(overviewData)
      setSystem(systemData)
    } catch (err) {
      setError(err instanceof Error ? err.message : '加载失败')
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => {
    fetchData()

    if (autoRefresh && refreshInterval > 0) {
      const timer = setInterval(fetchData, refreshInterval)
      return () => clearInterval(timer)
    }
  }, [fetchData, autoRefresh, refreshInterval])

  return {
    dashboard,
    overview,
    system,
    loading,
    error,
    refresh: fetchData,
  }
}
