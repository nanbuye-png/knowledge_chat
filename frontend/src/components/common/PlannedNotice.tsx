import { Construction } from 'lucide-react'

interface PlannedNoticeProps {
  /** 功能名（与 README「状态」列的写法保持一致） */
  feature: string
  /** 为什么没实现 / 现状说明 */
  reason?: string
  /** 已经真实可用的替代入口（可选） */
  available?: string
}

/**
 * 「Planned」统一标注（审计 §4）：
 *
 * 审计指出前端存在多处"看起来能用、实际 404"的空壳页面：AgentManagementPage 曾用
 * hardcoded 假数据渲染表格，AgentStudioPage/WorkflowStudioPage 曾真实发请求打不存在的
 * /agents、/workflows。现在假数据与空壳编排器都已删除，剩下的 Planned 页面必须显式标注，
 * 与 README 的措辞对齐 —— 宁可显示"未实现"，也不要让假数据冒充功能。
 */
export default function PlannedNotice({ feature, reason, available }: PlannedNoticeProps) {
  return (
    <div className="mb-6 rounded-2xl border border-amber-200/70 dark:border-amber-500/30 bg-amber-50/70 dark:bg-amber-900/10 p-4">
      <div className="flex items-start gap-3">
        <Construction className="w-5 h-5 text-amber-500 flex-shrink-0 mt-0.5" />
        <div className="text-sm">
          <p className="font-medium text-amber-800 dark:text-amber-200">
            {feature}：<span className="font-mono">Planned</span>（尚未实现）
          </p>
          {reason && (
            <p className="text-amber-700/90 dark:text-amber-300/80 mt-1">{reason}</p>
          )}
          {available && (
            <p className="text-amber-700/90 dark:text-amber-300/80 mt-1">{available}</p>
          )}
        </div>
      </div>
    </div>
  )
}
