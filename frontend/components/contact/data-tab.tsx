'use client';

import { useEffect } from 'react';
import type { Contact, Template } from '@/lib/api';
import { ContactInfoCard, CustomFieldsCard, SourcesCard, TemplateCard } from '@/components/contact/data-cards-info';
import { GroupsCard, RelatedCard, TagsCard } from '@/components/contact/data-cards-links';
import { LifeAreasCard, ScoresCard, SocialCard } from '@/components/contact/data-cards-profile';
import type { SaveContact } from '@/components/contact/types';

type Props = {
  contact: Contact;
  templates: Template[];
  onSave: SaveContact;
  /** Поле, к которому пришли из шапки: email, phone или ключ соцсети */
  focusField?: string;
};

/** «Данные»: бывшая правая колонка Dex — карточки в две колонки (на узком экране — в одну). */
export function DataTab({ contact, templates, onSave, focusField }: Props) {
  useEffect(() => {
    if (focusField === 'email' || focusField === 'phone') {
      document.getElementById('data-contact-info')?.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [focusField]);

  return (
    <div className="grid grid-cols-1 items-start gap-4 pt-4 xl:grid-cols-2">
      <div className="flex flex-col gap-4">
        <RelatedCard contact={contact} onSave={onSave} />
        <TagsCard contact={contact} onSave={onSave} />
        <ContactInfoCard contact={contact} onSave={onSave} />
        <TemplateCard contact={contact} templates={templates} onSave={onSave} />
        <CustomFieldsCard contact={contact} onSave={onSave} />
      </div>
      <div className="flex flex-col gap-4">
        <GroupsCard contact={contact} onSave={onSave} />
        <SocialCard contact={contact} onSave={onSave} focusKey={focusField} />
        <ScoresCard contact={contact} onSave={onSave} />
        <LifeAreasCard contact={contact} onSave={onSave} />
        <SourcesCard contact={contact} />
      </div>
    </div>
  );
}
