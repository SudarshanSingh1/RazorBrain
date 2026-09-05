import React from 'react';

export interface Column<T> {
  header: React.ReactNode;
  accessorKey?: keyof T;
  cell?: (item: T) => React.ReactNode;
  className?: string;
}

export interface DataTableProps<T> {
  data: T[];
  columns: Column<T>[];
  keyExtractor: (item: T, index: number) => string;
  onRowClick?: (item: T) => void;
  className?: string;
  emptyMessage?: string;
}

export function DataTable<T>({
  data,
  columns,
  keyExtractor,
  onRowClick,
  className = '',
  emptyMessage = 'No data available'
}: DataTableProps<T>) {
  return (
    <div className={`w-full overflow-x-auto ${className}`}>
      <table className="w-full text-left border-collapse">
        <thead>
          <tr className="bg-[rgba(25,48,80,0.7)] border-b border-border-subtle">
            {columns.map((col, idx) => (
              <th
                key={idx}
                className={`px-4 py-3 text-[11px] md:text-[12px] font-semibold text-text-muted uppercase tracking-[0.05em] whitespace-nowrap ${col.className || ''}`}
              >
                {col.header}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {data.length === 0 ? (
            <tr>
              <td colSpan={columns.length} className="px-4 py-8 text-center text-text-muted text-[13px]">
                {emptyMessage}
              </td>
            </tr>
          ) : (
            data.map((item, rowIdx) => (
              <tr
                key={keyExtractor(item, rowIdx)}
                onClick={() => onRowClick && onRowClick(item)}
                className={`border-b border-[rgba(255,255,255,0.05)] transition-colors duration-150 ${onRowClick ? 'cursor-pointer hover:bg-[rgba(47,128,237,0.04)]' : 'hover:bg-[rgba(255,255,255,0.01)]'} last:border-b-0`}
              >
                {columns.map((col, colIdx) => (
                  <td
                    key={colIdx}
                    className={`px-4 py-3.5 text-[12px] md:text-[13px] text-text-primary ${col.className || ''}`}
                  >
                    {col.cell ? col.cell(item) : col.accessorKey ? (item[col.accessorKey] as any) : null}
                  </td>
                ))}
              </tr>
            ))
          )}
        </tbody>
      </table>
    </div>
  );
}

export const LinkText: React.FC<{ children: React.ReactNode; className?: string; onClick?: (e: any) => void }> = ({ children, className = '', onClick }) => (
  <span onClick={onClick} className={`text-[#4ea1ff] hover:text-brand-bright hover:underline cursor-pointer truncate max-w-[120px] md:max-w-[200px] block ${className}`} title={typeof children === 'string' ? children : undefined}>
    {children}
  </span>
);
