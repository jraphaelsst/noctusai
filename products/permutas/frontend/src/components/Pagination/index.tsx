import { memo } from 'react'
import styled from 'styled-components'
import { color, spacing, radius } from '../../styles'

const PaginationContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  gap: ${spacing.sm};
  margin-top: ${spacing.lg};
  padding: ${spacing.md};
`

const PaginationButton = styled.button<{ $active?: boolean }>`
  padding: ${spacing.xs} ${spacing.sm};
  min-width: 36px;
  border: 1px solid ${({ $active }) => $active ? color.primary : color.border};
  border-radius: ${radius.sm};
  background: ${({ $active }) => $active ? color.primary : 'white'};
  color: ${({ $active }) => $active ? 'white' : color.text};
  cursor: pointer;
  font-weight: ${({ $active }) => $active ? '600' : '400'};
  transition: all 0.2s ease;

  &:hover:not(:disabled) {
    background: ${({ $active }) => $active ? color.primaryDark : color.backgroundDark};
  }

  &:disabled {
    opacity: 0.5;
    cursor: not-allowed;
  }
`

const PaginationInfo = styled.span`
  color: ${color.textLight};
  font-size: 14px;
`

type PaginationProps = {
  currentPage: number
  totalPages: number
  totalCount: number
  onPageChange: (page: number) => void
}

const Pagination = ({ currentPage, totalPages, totalCount, onPageChange }: PaginationProps) => {
  if (totalPages <= 1) return null

  const getVisiblePages = () => {
    const pages: (number | string)[] = []
    const maxVisible = 5
    
    if (totalPages <= maxVisible) {
      for (let i = 1; i <= totalPages; i++) {
        pages.push(i)
      }
    } else {
      if (currentPage <= 3) {
        for (let i = 1; i <= 4; i++) {
          pages.push(i)
        }
        pages.push('...')
        pages.push(totalPages)
      } else if (currentPage >= totalPages - 2) {
        pages.push(1)
        pages.push('...')
        for (let i = totalPages - 3; i <= totalPages; i++) {
          pages.push(i)
        }
      } else {
        pages.push(1)
        pages.push('...')
        for (let i = currentPage - 1; i <= currentPage + 1; i++) {
          pages.push(i)
        }
        pages.push('...')
        pages.push(totalPages)
      }
    }
    
    return pages
  }

  return (
    <PaginationContainer>
      <PaginationButton 
        onClick={() => onPageChange(currentPage - 1)}
        disabled={currentPage === 1}
      >
        Anterior
      </PaginationButton>
      
      {getVisiblePages().map((page, index) => (
        typeof page === 'number' ? (
          <PaginationButton
            key={index}
            $active={page === currentPage}
            onClick={() => onPageChange(page)}
          >
            {page}
          </PaginationButton>
        ) : (
          <PaginationInfo key={index}>{page}</PaginationInfo>
        )
      ))}
      
      <PaginationButton 
        onClick={() => onPageChange(currentPage + 1)}
        disabled={currentPage === totalPages}
      >
        Próximo
      </PaginationButton>
      
      <PaginationInfo>
        ({totalCount} registros)
      </PaginationInfo>
    </PaginationContainer>
  )
}

export default memo(Pagination)
