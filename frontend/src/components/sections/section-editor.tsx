import type { Proposal, SectionType } from '../../types/proposal'
import { SECTION_ORDER, SECTION_TITLES } from '../../types/proposal'
import { SectionBlock } from './section-block'

interface Props {
  proposal: Proposal
}

export function SectionEditor({ proposal }: Props) {
  const items = SECTION_ORDER
    .map((type) => ({ type: type as SectionType, section: proposal[type as SectionType] }))
    .filter((item) => item.section !== null)

  if (items.length === 0) {
    return (
      <div className="text-sm text-stone-500 text-center py-12">
        Sections are being drafted… this takes about 30 seconds.
      </div>
    )
  }

  return (
    <div className="space-y-6">
      {items.map(({ type, section }) => (
        <SectionBlock
          key={type}
          proposalId={proposal.id}
          type={type}
          title={SECTION_TITLES[type]}
          section={section!}
        />
      ))}
    </div>
  )
}
