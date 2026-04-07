export interface Client {
  id: string
  name: string
  slug: string
  industry: string | null
  size: string | null
  contacts: ContactInfo[]
  notes: string | null
  tags: string[]
  context_profile: Record<string, unknown>
  created_at: string
  updated_at: string
}

export interface ContactInfo {
  name: string
  role?: string
  email?: string
  phone?: string
}

export interface ClientCreate {
  name: string
  industry?: string
  size?: string
  contacts?: ContactInfo[]
  notes?: string
  tags?: string[]
}

export interface ClientUpdate {
  name?: string
  industry?: string
  size?: string
  contacts?: ContactInfo[]
  notes?: string
  tags?: string[]
}
