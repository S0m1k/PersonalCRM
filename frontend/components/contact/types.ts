import type { ContactUpdate } from '@/lib/api';

/**
 * Сохранение правки карточки: оптимистично, с откатом. Возвращает текст ошибки или null.
 * silent — не показывать toast (ошибку покажет вызывающий, например у соцсетей).
 */
export type SaveContact = (patch: ContactUpdate, options?: { silent?: boolean }) => Promise<string | null>;
