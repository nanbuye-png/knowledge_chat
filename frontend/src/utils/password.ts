/**
 * 密码强度校验工具。
 *
 * 规则与后端 backend/app/core/password_policy.py 严格保持一致，
 * 避免出现"前端提示至少 6 位、后端要求 12 位"导致注册必然失败的体验问题：
 * - 至少 12 位
 * - 至少一个数字
 * - 至少一个大写字母
 * - 至少一个小写字母
 * - 至少一个特殊字符（非字母数字、非空白字符）
 */

export const PASSWORD_MIN_LENGTH = 12

const HAS_DIGIT = /\d/
const HAS_UPPER = /[A-Z]/
const HAS_LOWER = /[a-z]/
const HAS_SPECIAL = /[^\w\s]/

/**
 * 校验密码强度。
 *
 * @param password 待校验的明文密码
 * @returns 错误信息列表，为空表示通过校验
 */
export function validatePasswordStrength(password: string): string[] {
  const errors: string[] = []

  if (password.length < PASSWORD_MIN_LENGTH) {
    errors.push(`密码长度至少需要 ${PASSWORD_MIN_LENGTH} 位，当前为 ${password.length} 位`)
  }
  if (!HAS_DIGIT.test(password)) {
    errors.push('密码必须包含至少一个数字')
  }
  if (!HAS_UPPER.test(password)) {
    errors.push('密码必须包含至少一个大写字母')
  }
  if (!HAS_LOWER.test(password)) {
    errors.push('密码必须包含至少一个小写字母')
  }
  if (!HAS_SPECIAL.test(password)) {
    errors.push('密码必须包含至少一个特殊字符（如 @#$%^&* 等）')
  }

  return errors
}
