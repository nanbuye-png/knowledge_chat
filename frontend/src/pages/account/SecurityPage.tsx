import { useState } from 'react'
import { Shield, Key, Lock, CheckCircle, AlertTriangle } from 'lucide-react'
import { useAuthStore } from '../../store/auth'
import apiClient from '../../api/client'

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

    if (newPw.length < 6) { setMsg('新密码至少 6 位'); return }
    if (newPw !== confirmPw) { setMsg('两次密码不一致'); return }

    setChanging(true)
    try {
      await apiClient.post('/auth/change-password', {
        current_password: currentPw,
        new_password: newPw,
      })
      setMsg('✅ 密码修改成功')
      setCurrentPw('')
      setNewPw('')
      setConfirmPw('')
    } catch (err: any) {
      setMsg(err?.response?.data?.detail || '密码修改失败')
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
            <span className="text-emerald-600 flex items-center gap-1"><CheckCircle className="w-3 h-3" /> Strong</span>
          </div>
        </div>
      </div>
    </div>
  )
}