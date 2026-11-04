import { getContacts, type Contact } from './api';

const PAGE_SIZE = 200;
const MAX_CONTACTS = 2000;

/** Все контакты постранично (бэкенд отдаёт до 200 за запрос); потолок — 2000. */
export async function loadAllContacts(): Promise<Contact[]> {
  const all: Contact[] = [];
  while (all.length < MAX_CONTACTS) {
    const page = await getContacts({ limit: PAGE_SIZE, skip: all.length });
    all.push(...page);
    if (page.length < PAGE_SIZE) break;
  }
  return all;
}

export const ALL_CONTACTS_KEY = 'contacts:all';
