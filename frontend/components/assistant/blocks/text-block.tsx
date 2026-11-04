import type { TextBlock } from '@/lib/api-assistant';

/** Обычный текст с переносами строк. Без HTML: ответ модели — недоверенные данные. */
export function TextBlockView({ block }: { block: TextBlock }) {
  return <p className="whitespace-pre-line text-[15px] leading-relaxed">{block.text}</p>;
}
