import { useState, useRef, useEffect } from 'react';
import { DayPicker, type DateRange } from 'react-day-picker';
import { format, parse } from 'date-fns';
import { ru } from 'date-fns/locale';
import { Calendar, X } from 'lucide-react';

interface DateRangePickerProps {
  dateFrom: string;
  dateTo: string;
  onChange: (dateFrom: string, dateTo: string) => void;
  className?: string;
}

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

  return (
    <div ref={containerRef} className={`relative ${className}`}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        className="input w-full text-left flex items-center justify-between gap-2 text-sm"
      >
        <div className="flex items-center gap-2">
          <Calendar className="w-4 h-4 text-slate-500" />
          <span className={selected.from ? 'text-slate-200' : 'text-slate-500'}>
            {displayValue()}
          </span>
        </div>
        {selected.from && (
          <X
            className="w-4 h-4 text-slate-500 hover:text-slate-300"
            onClick={clearSelection}
          />
        )}
      </button>

      {isOpen && (
        <div className="absolute z-50 mt-1 bg-slate-800 border border-slate-700 shadow-lg p-3">
          <style>{`
            .rdp-root {
              --rdp-accent-color: #475569;
              --rdp-accent-background-color: #334155;
              --rdp-day-height: 32px;
              --rdp-day-width: 32px;
              --rdp-selected-font: inherit;
              font-family: inherit;
            }
            .rdp-month_caption {
              font-size: 13px;
              font-weight: 500;
              color: #94a3b8;
              padding: 0 4px 8px;
            }
            .rdp-button_previous,
            .rdp-button_next {
              width: 24px;
              height: 24px;
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
              font-size: 11px;
              font-weight: 500;
              color: #64748b;
              text-transform: uppercase;
            }
            .rdp-day {
              font-size: 13px;
              color: #cbd5e1;
            }
            .rdp-day button {
              width: 32px;
              height: 32px;
              background: transparent;
              border: none;
              color: inherit;
              cursor: pointer;
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
      )}
    </div>
  );
}
