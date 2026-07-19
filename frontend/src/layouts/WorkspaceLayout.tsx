import React from 'react'

/**
 * 普通用户工作空间容器布局。
 * 为 USER 角色提供简洁的工作区框架。
 */
export default function WorkspaceLayout({ children }: { children: React.ReactNode }) {
  return (
    <div className="h-full overflow-hidden bg-slate-50 dark:bg-slate-900">
      {children}
    </div>
  )
}
