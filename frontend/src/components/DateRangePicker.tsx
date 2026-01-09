import { useState, useRef, useEffect } from 'react';
import { DayPicker, type DateRange } from 'react-day-picker';
import { format, parse, startOfMonth, subDays, startOfDay } from 'date-fns';
import { ru } from 'date-fns/locale';
import { Calendar, X } from 'lucide-react';

interface DateRangePickerProps {
  dateFrom: string;
  dateTo: string;
  onChange: (dateFrom: string, dateTo: string) => void;
  className?: string;
}

interface DatePreset {
  label: string;
  getRange: () => { from: Date; to: Date };
}

const datePresets: DatePreset[] = [
  {
    label: 'Сегодня',
    getRange: () => {
      const today = startOfDay(new Date());
      return { from: today, to: today };
    },
  },
  {
    label: 'Вчера',
    getRange: () => {
      const yesterday = startOfDay(subDays(new Date(), 1));
      return { from: yesterday, to: yesterday };
    },
  },
  {
    label: '3 дня',
    getRange: () => {
      const today = startOfDay(new Date());
      return { from: subDays(today, 2), to: today };
    },
  },
  {
    label: '7 дней',
    getRange: () => {
      const today = startOfDay(new Date());
      return { from: subDays(today, 6), to: today };
    },
  },
  {
    label: '30 дней',
    getRange: () => {
      const today = startOfDay(new Date());
      return { from: subDays(today, 29), to: today };
    },
  },
  {
    label: 'Месяц',
    getRange: () => {
      const today = startOfDay(new Date());
      return { from: startOfMonth(today), to: today };
    },
  },
];

export function DateRangePicker({ dateFrom, dateTo, onChange, className = '' }: DateRangePickerProps) {
  const [isOpen, setIsOpen] = useState(false);
  const [selected, setSelected] = useState<{ from: Date | undefined; to: Date | undefined }>(() => {
    const from = dateFrom ? parse(dateFrom, 'yyyy-MM-dd', new Date()) : undefined;
    const to = dateTo ? parse(dateTo, 'yyyy-MM-dd', new Date()) : undefined;
    return { from, to };
  });

  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const from = dateFrom ? parse(dateFrom, 'yyyy-MM-dd', new Date()) : undefined;
    const to = dateTo ? parse(dateTo, 'yyyy-MM-dd', new Date()) : undefined;
    setSelected({ from, to });
  }, [dateFrom, dateTo]);

  useEffect(() => {
    function handleClickOutside(event: MouseEvent) {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setIsOpen(false);
      }
    }
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  const handleSelect = (range: DateRange | undefined) => {
    if (!range) {
      setSelected({ from: undefined, to: undefined });
      return;
    }

    setSelected({ from: range.from, to: range.to });

    if (range.from && range.to) {
      onChange(
        format(range.from, 'yyyy-MM-dd'),
        format(range.to, 'yyyy-MM-dd')
      );
    } else if (range.from && !range.to) {
      // Single day selected
      onChange(
        format(range.from, 'yyyy-MM-dd'),
        format(range.from, 'yyyy-MM-dd')
      );
    }
  };

  const displayValue = () => {
    if (!selected.from) return 'Выберите период';

    const fromStr = format(selected.from, 'dd.MM.yyyy');

    if (!selected.to || selected.from.getTime() === selected.to.getTime()) {
      return fromStr;
    }

    const toStr = format(selected.to, 'dd.MM.yyyy');
    return `${fromStr} – ${toStr}`;
  };

  const clearSelection = (e: React.MouseEvent) => {
    e.stopPropagation();
    setSelected({ from: undefined, to: undefined });
    onChange('', '');
  };

  const applyPreset = (preset: DatePreset) => {
    const range = preset.getRange();
    setSelected({ from: range.from, to: range.to });
    onChange(
      format(range.from, 'yyyy-MM-dd'),
      format(range.to, 'yyyy-MM-dd')
    );
  };

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="input w-full text-left flex items-center justify-between gap-2 text-sm"
      >
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-zinc-500" />
          <span className={selected.from ? 'text-zinc-200' : 'text-zinc-500'}>
            {displayValue()}
          </span>
        </div>
        {selected.from && (
          <X
            className="w-4 h-4 text-zinc-500 hover:text-zinc-300"
            onClick={clearSelection}
          />
        )}
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 left-0 right-0 sm:left-auto sm:right-auto w-auto max-w-[calc(100vw-2rem)] sm:max-w-fit bg-zinc-800 border border-zinc-700 rounded-lg shadow-lg overflow-hidden">
          <style>{`
            .rdp-root {
              --rdp-accent-color: #475569;
              --rdp-accent-background-color: #334155;
              --rdp-day-height: 32px;
              --rdp-day-width: 32px;
              --rdp-selected-font: inherit;
              font-family: inherit;
            }
            @media (min-width: 640px) {
              .rdp-root {
                --rdp-day-height: 38px;
                --rdp-day-width: 38px;
              }
              .rdp-day button {
                width: 38px;
                height: 38px;
              }
            }
            .rdp-month_caption {
              font-size: 14px;
              font-weight: 500;
              color: #94a3b8;
              padding: 0 4px 8px;
            }
            .rdp-button_previous,
            .rdp-button_next {
              width: 28px;
              height: 28px;
              color: #64748b;
              background: transparent;
              border: none;
              cursor: pointer;
            }
            .rdp-button_previous:hover,
            .rdp-button_next:hover {
              color: #94a3b8;
            }
            .rdp-weekday {
              font-size: 12px;
              font-weight: 500;
              color: #64748b;
              text-transform: uppercase;
            }
            .rdp-day {
              font-size: 14px;
              color: #cbd5e1;
            }
            .rdp-day button {
              width: 32px;
              height: 32px;
              background: transparent;
              border: none;
              color: inherit;
              cursor: pointer;
              border-radius: 4px;
            }
            .rdp-day button:hover {
              background: #334155;
            }
            .rdp-selected .rdp-day_button,
            .rdp-range_start .rdp-day_button,
            .rdp-range_end .rdp-day_button {
              background: #475569 !important;
              color: #f1f5f9 !important;
            }
            .rdp-range_middle .rdp-day_button {
              background: #334155 !important;
              color: #cbd5e1 !important;
            }
            .rdp-today .rdp-day_button {
              font-weight: 600;
              color: #e2e8f0;
            }
            .rdp-disabled .rdp-day_button {
              color: #475569;
              cursor: not-allowed;
            }
            .rdp-outside .rdp-day_button {
              color: #475569;
            }
          `}</style>
          <div className="flex flex-col sm:flex-row sm:w-fit">
            {/* Presets panel - horizontal on mobile, vertical on desktop */}
            <div className="flex flex-wrap gap-1 p-2 border-b sm:border-b-0 sm:border-r border-zinc-700 sm:flex-col sm:gap-0 sm:p-0 sm:py-2 sm:w-28">
              {datePresets.map((preset) => (
                <button
                  key={preset.label}
                  type="button"
                  onClick={() => applyPreset(preset)}
                  className="px-2 py-1.5 sm:px-3 sm:py-2 text-xs sm:text-sm text-zinc-300 hover:bg-zinc-700 hover:text-white transition-colors whitespace-nowrap rounded sm:rounded-none sm:w-full sm:text-left bg-zinc-700/50 sm:bg-transparent"
                >
                  {preset.label}
                </button>
              ))}
            </div>
            {/* Calendar */}
            <div className="p-2 sm:p-3 flex justify-center">
              <DayPicker
                mode="range"
                selected={selected}
                onSelect={handleSelect}
                locale={ru}
                numberOfMonths={1}
                defaultMonth={selected.from || new Date()}
                disabled={{ after: new Date() }}
                showOutsideDays
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
