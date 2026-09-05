import React from 'react';
import { Search } from 'lucide-react';

export interface SearchInputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  containerClassName?: string;
}

export const SearchInput: React.FC<SearchInputProps> = ({ containerClassName = '', className = '', ...props }) => {
  return (
    <div className={`relative ${containerClassName}`}>
      <div className="absolute inset-y-0 left-0 pl-3 flex items-center pointer-events-none text-text-muted">
        <Search size={16} />
      </div>
      <input
        type="text"
        className={`w-full bg-[rgba(9,24,45,0.8)] border border-[rgba(120,150,210,0.2)] rounded-[8px] pl-9 pr-4 py-2 text-[14px] text-text-primary placeholder:text-text-muted focus:outline-none focus:border-brand focus:shadow-[0_0_0_3px_rgba(47,128,237,0.12)] transition-all duration-200 ${className}`}
        {...props}
      />
    </div>
  );
};
