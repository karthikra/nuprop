export interface GlobalsValue {
  pass_through_markup: number
  standard_options: number
  standard_revisions: number
}

interface Props {
  value: GlobalsValue
  onChange: (next: GlobalsValue) => void
}

export function GlobalsStep({ value, onChange }: Props) {
  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-6">
      <Field
        label="Pass-through markup"
        suffix="%"
        help="What you charge clients on top of pass-through costs (print, photography, third-party services)"
        value={Math.round(value.pass_through_markup * 100)}
        onChange={(v) => onChange({ ...value, pass_through_markup: v / 100 })}
      />
      <Field
        label="Standard options per deliverable"
        help="How many design options or concepts you include in the base price for each deliverable"
        value={value.standard_options}
        onChange={(v) => onChange({ ...value, standard_options: v })}
      />
      <Field
        label="Standard revision rounds"
        help="How many rounds of revisions are included before additional rounds are billed at hourly rates"
        value={value.standard_revisions}
        onChange={(v) => onChange({ ...value, standard_revisions: v })}
      />
    </div>
  )
}

function Field({
  label,
  suffix,
  help,
  value,
  onChange,
}: {
  label: string
  suffix?: string
  help: string
  value: number
  onChange: (n: number) => void
}) {
  return (
    <label className="block">
      <span className="block text-xs font-medium text-stone-900 mb-1">{label}</span>
      <div className="flex items-center gap-1">
        <input
          key={value}
          type="number"
          aria-label={label}
          defaultValue={value}
          onChange={(e) => onChange(Number(e.target.value) || 0)}
          className="w-20 rounded-md border border-stone-300 px-2 py-1 text-sm focus:outline-none focus:ring-1 focus:ring-stone-900"
        />
        {suffix && <span className="text-sm text-stone-500">{suffix}</span>}
      </div>
      <p className="text-xs text-stone-500 mt-1 leading-snug">{help}</p>
    </label>
  )
}
