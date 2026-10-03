import { useState } from 'react'
import { Shield, Key, Lock, CheckCircle, AlertTriangle } from 'lucide-react'
import { useAuthStore } from '../../store/auth'
import apiClient from '../../api/client'

/**
 * 密码强度（与后端 core/password_policy.py **逐条对应**）
 * ---------------------------------------------------------------------------
 * 后端 validate_password_strength：≥12 位 + 数字 + 大写 + 小写 + 特殊字符。
 * 这里此前只判 `length < 6`（与后端策略不一致，用户会先被放过去再吃 400），
 * 现在前端提示与后端同源，最多只做"提前告知"，最终仍以后端 400 为准。
 */
const PASSWORD_RULES: { test: (pw: string) => boolean; label: string }[] = [
  { test: (pw) => pw.length >= 12, label: '至少 12 位' },
  { test: (pw) => /\d/.test(pw), label: '含数字' },
  { test: (pw) => /[A-Z]/.test(pw), label: '含大写字母' },
  { test: (pw) => /[a-z]/.test(pw), label: '含小写字母' },
  { test: (pw) => /[^\w\s]/.test(pw), label: '含特殊字符' },
]

function policyErrorOf(password: string): string | null {
  const failed = PASSWORD_RULES.filter((rule) => !rule.test(password))
  if (failed.length === 0) return null
  return `新密码需满足：${failed.map((rule) => rule.label).join('、')}`
}

export default function SecurityPage() {
  const { user } = useAuthStore()

  const [currentPw, setCurrentPw] = useState('')
  const [newPw, setNewPw] = useState('')
  const [confirmPw, setConfirmPw] = useState('')
  const [changing, setChanging] = useState(false)
  const [msg, setMsg] = useState('')

  const handleChangePassword = async (e: React.FormEvent) => {
    e.preventDefault()
    setMsg('')

    if (!currentPw) { setMsg('请输入当前密码'); return }
    const policyError = policyErrorOf(newPw)
    if (policyError) { setMsg(policyError); return }
    if (newPw !== confirmPw) { setMsg('两次密码不一致'); return }

    setChanging(true)
    try {
      const res = await apiClient.post('/auth/change-password', {
        current_password: currentPw,
        new_password: newPw,
      })
      // 后端改密码后会作废其他设备的 Session（当前设备保留）
      const revoked = Number(res.data?.revoked_sessions ?? 0)
      setMsg(revoked > 0
        ? `✅ 密码修改成功，已退出其他 ${revoked} 台设备的登录`
        : '✅ 密码修改成功')
      setCurrentPw('')
      setNewPw('')
      setConfirmPw('')
    } catch (err) {
      // 响应拦截器已把错误统一成 `new Error(message)`（见 api/client.ts）。
      // 旧代码只读 err.response.data.detail，会漏掉统一信封的顶层 message。
      setMsg(err instanceof Error && err.message ? err.message : '密码修改失败')
    } finally {
      setChanging(false)
    }
  }

  return (
    <div className="p-8 max-w-2xl">
      <h2 className="text-xl font-bold text-slate-800 dark:text-white mb-6 flex items-center gap-2">
        <Shield className="w-5 h-5 text-primary-500" />
        Security
      </h2>

      {/* Change Password */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-6 mb-6">
        <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-4">
          <Lock className="w-4 h-4 text-slate-400" />
          Change Password
        </h3>

        <form onSubmit={handleChangePassword} className="space-y-3">
          <input
            type="password"
            placeholder="Current Password"
            value={currentPw}
            onChange={(e) => setCurrentPw(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500"
          />
          <input
            type="password"
            placeholder="New Password"
            value={newPw}
            onChange={(e) => setNewPw(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500"
          />
          <p className="text-[11px] text-slate-400 leading-relaxed">
            至少 12 位，且包含大写字母、小写字母、数字与特殊字符
          </p>
          <input
            type="password"
            placeholder="Confirm New Password"
            value={confirmPw}
            onChange={(e) => setConfirmPw(e.target.value)}
            className="w-full px-3 py-2 text-sm rounded-xl border border-slate-300 dark:border-slate-600 bg-slate-50 dark:bg-slate-700 text-slate-800 dark:text-white outline-none focus:ring-2 focus:ring-primary-500"
          />

          {msg && (
            <p className={`text-sm ${msg.includes('✅') ? 'text-emerald-600' : 'text-red-500'}`}>{msg}</p>
          )}

          <button
            type="submit"
            disabled={changing}
            className="px-4 py-2 text-sm font-medium rounded-xl bg-primary-500 text-white hover:bg-primary-600 disabled:opacity-50 transition-colors"
          >
            {changing ? 'Updating...' : 'Update Password'}
          </button>
        </form>
      </div>

      {/* Security Status */}
      <div className="rounded-2xl bg-white dark:bg-slate-800 border border-slate-200 dark:border-slate-700 p-6">
        <h3 className="font-semibold text-slate-800 dark:text-white flex items-center gap-2 mb-3">
          <CheckCircle className="w-4 h-4 text-emerald-500" />
          Security Status
        </h3>
        <div className="space-y-2 text-sm">
          <div className="flex items-center justify-between py-1">
            <span className="text-slate-500">Account Protection</span>
            <span className="text-emerald-600 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Active</span>
          </div>
          <div className="flex items-center justify-between py-1">
            <span className="text-slate-500">Login Protection</span>
            <span className="text-emerald-600 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> 5 attempts / 15 min</span>
          </div>
          <div className="flex items-center justify-between py-1">
            <span className="text-slate-500">Password Policy</span>
            <span className="text-emerald-600 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> ≥12 位 + 大小写 + 数字 + 特殊字符</span>
          </div>
        </div>
      </div>
    </div>
  )
}