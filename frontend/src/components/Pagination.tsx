import { memo, useMemo } from 'react';
import { ChevronLeft, ChevronRight, ChevronsLeft, ChevronsRight } from 'lucide-react';

interface PaginationProps {
  currentPage: number;
  totalPages: number;
  totalItems: number;
  pageSize: number;
  onPageChange: (page: number) => void;
}

export const Pagination = memo(function Pagination({ currentPage, totalPages, totalItems, pageSize, onPageChange }: PaginationProps) {
  const startItem = (currentPage - 1) * pageSize + 1;
  const endItem = Math.min(currentPage * pageSize, totalItems);

  const pageNumbers = useMemo(() => {
    const pages: (number | string)[] = [];
    const maxVisible = 5;
    
    if (totalPages <= maxVisible + 2) {
      // Show all pages
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i);
      }
    } else {
      // Always show first page
      pages.push(1);
      
      if (currentPage > 3) {
        pages.push('...');
      }
      
      // Pages around current
      const start = Math.max(2, currentPage - 1);
      const end = Math.min(totalPages - 1, currentPage + 1);
      
      for (let i = start; i <= end; i++) {
        pages.push(i);
      }
      
      if (currentPage < totalPages - 2) {
        pages.push('...');
      }
      
      // Always show last page
      if (totalPages > 1) {
        pages.push(totalPages);
      }
    }
    
    return pages;
  }, [currentPage, totalPages]);

  if (totalPages <= 1) {
    return (
      <div className="text-sm text-zinc-400">
        Всего: {totalItems} записей
      </div>
    );
  }

  return (
    <div className="flex flex-col sm:flex-row items-center justify-between gap-3 sm:gap-4">
      <div className="text-xs sm:text-sm text-zinc-400">
        Показано {startItem}–{endItem} из {totalItems}
      </div>

      <div className="flex items-center gap-1">
        {/* First page */}
        <button
          onClick={() => onPageChange(1)}
          disabled={currentPage === 1}
          className="p-1.5 sm:p-1.5 rounded hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-400 hover:text-white"
          title="Первая страница"
        >
          <ChevronsLeft className="w-5 h-5 sm:w-4 sm:h-4" />
        </button>

        {/* Previous page */}
        <button
          onClick={() => onPageChange(currentPage - 1)}
          disabled={currentPage === 1}
          className="p-1.5 sm:p-1.5 rounded hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-400 hover:text-white"
          title="Предыдущая страница"
        >
          <ChevronLeft className="w-5 h-5 sm:w-4 sm:h-4" />
        </button>

        {/* Mobile: Simple page indicator */}
        <div className="sm:hidden px-3 py-1 text-sm text-white">
          {currentPage} / {totalPages}
        </div>

        {/* Desktop: Page numbers */}
        <div className="hidden sm:flex items-center gap-1">
          {pageNumbers.map((page, index) => (
            typeof page === 'number' ? (
              <button
                key={index}
                onClick={() => onPageChange(page)}
                className={`min-w-[32px] h-8 px-2 rounded text-sm font-medium transition-colors ${
                  page === currentPage
                    ? 'bg-blue-600 text-white'
                    : 'hover:bg-zinc-700 text-zinc-400 hover:text-white'
                }`}
              >
                {page}
              </button>
            ) : (
              <span key={index} className="px-1 text-zinc-500">...</span>
            )
          ))}
        </div>

        {/* Next page */}
        <button
          onClick={() => onPageChange(currentPage + 1)}
          disabled={currentPage === totalPages}
          className="p-1.5 sm:p-1.5 rounded hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-400 hover:text-white"
          title="Следующая страница"
        >
          <ChevronRight className="w-5 h-5 sm:w-4 sm:h-4" />
        </button>

        {/* Last page */}
        <button
          onClick={() => onPageChange(totalPages)}
          disabled={currentPage === totalPages}
          className="p-1.5 sm:p-1.5 rounded hover:bg-zinc-700 disabled:opacity-40 disabled:cursor-not-allowed text-zinc-400 hover:text-white"
          title="Последняя страница"
        >
          <ChevronsRight className="w-5 h-5 sm:w-4 sm:h-4" />
        </button>
      </div>
    </div>
  );
});
