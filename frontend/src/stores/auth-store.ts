import { create } from 'zustand'
import { api } from '../api/client'
import type { AgencyResponse, TokenResponse, UserResponse } from '../types/auth'

interface AuthState {
  token: string | null
  user: UserResponse | null
  agency: AgencyResponse | null
  isLoading: boolean

  register: (email: string, password: string, fullName: string, agencyName: string) => Promise<void>
  login: (email: string, password: string) => Promise<void>
  logout: () => void
  fetchMe: () => Promise<void>
  fetchAgency: () => Promise<void>
  initialize: () => Promise<void>
}

export const useAuthStore = create<AuthState>((set, get) => ({
  token: localStorage.getItem('nuprop_token'),
  user: null,
  agency: null,
  isLoading: true,

  register: async (email, password, fullName, agencyName) => {
    const { data } = await api.post<TokenResponse>('/auth/register', {
      email,
      password,
      full_name: fullName,
      agency_name: agencyName,
    })
    localStorage.setItem('nuprop_token', data.access_token)
    set({ token: data.access_token })
    await get().fetchMe()
    await get().fetchAgency()
  },

  login: async (email, password) => {
    const { data } = await api.post<TokenResponse>('/auth/login', { email, password })
    localStorage.setItem('nuprop_token', data.access_token)
    set({ token: data.access_token })
    await get().fetchMe()
    await get().fetchAgency()
  },

  logout: () => {
    localStorage.removeItem('nuprop_token')
    set({ token: null, user: null, agency: null })
  },

  fetchMe: async () => {
    const { data } = await api.get<UserResponse>('/auth/me')
    set({ user: data })
  },

  fetchAgency: async () => {
    const { data } = await api.get<AgencyResponse>('/agencies/me')
    set({ agency: data })
  },

  initialize: async () => {
    const token = localStorage.getItem('nuprop_token')
    if (!token) {
      set({ isLoading: false })
      return
    }
    try {
      await get().fetchMe()
      await get().fetchAgency()
    } catch {
      localStorage.removeItem('nuprop_token')
      set({ token: null })
    }
    set({ isLoading: false })
  },
}))
