export interface StrategyTemplate {
  id: string
  template_key: string
  name: string
  description: string | null
  category: string
  config: TemplateConfig
  is_system: boolean
  created_at: string
}

export interface TemplateConfig {
  brief_intake?: {
    required_questions?: string[]
    optional_questions?: string[]
    auto_detect_signals?: string[]
  }
  research?: {
    client_queries?: string[]
    benchmark_queries?: string[]
    benchmark_categories?: string[]
  }
  cost_model?: {
    typical_deliverables?: string[]
    default_multipliers?: string[]
    pricing_framing?: string
    pricing_anchor_text?: string
  }
  narrative?: {
    letter_strategy?: string
    letter_opening_instruction?: string
    letter_tone_words?: string[]
    letter_avoid_words?: string[]
    scope_detail_level?: string
    rationale_depth?: string
  }
  output?: {
    site_theme?: string
    sections_include?: string[]
    sections_skip?: string[]
    suggested_formats?: string[]
    demo_embed_eligible?: boolean
  }
}

export const CATEGORY_COLOURS: Record<string, string> = {
  brand: 'bg-purple-100 text-purple-700',
  technology: 'bg-blue-100 text-blue-700',
  campaign: 'bg-amber-100 text-amber-700',
  retainer: 'bg-green-100 text-green-700',
  film: 'bg-red-100 text-red-700',
  consulting: 'bg-stone-100 text-stone-600',
  spatial: 'bg-cyan-100 text-cyan-700',
}
