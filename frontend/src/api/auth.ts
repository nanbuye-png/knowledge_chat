import apiClient from './client'

export interface LoginRequest {
  username: string
  password: string
}

export interface RegisterRequest {
  username: string
  email?: string | null
  password: string
}

export interface TokenResponse {
  access_token: string
  token_type: string
}

export interface UserInfo {
  id: number
  username: string
  email: string | null
  role?: string | null
  created_at: string | null
}

export async function login(data: LoginRequest): Promise<TokenResponse> {
  const response = await apiClient.post('/auth/login', {
    username: data.username,
    password: data.password,
  })
  return response.data
}

export async function register(data: RegisterRequest): Promise<UserInfo> {
  const response = await apiClient.post('/auth/register', {
    username: data.username,
    email: data.email,
    password: data.password,
  })
  return response.data
}

export async function getMe(): Promise<UserInfo> {
  const response = await apiClient.get('/auth/me')
  return response.data
}