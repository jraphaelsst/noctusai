import { useState, useMemo, useEffect, useRef, useCallback } from 'react'
import styled from 'styled-components'
import swal from 'sweetalert2'
import { color, spacing } from '../../styles'
import TableSkeleton from '../TableSkeleton'

const TableWrapper = styled.div`
  background: ${color.cardBg};
  border: 1px solid ${color.border};
  overflow: hidden;
  margin-top: ${spacing.lg};
`

const FiltersContainer = styled.div`
  display: flex;
  flex-wrap: wrap;
  gap: ${spacing.md};
  padding: ${spacing.lg};
  background: ${color.backgroundDark};
  border-bottom: 1px solid ${color.border};
`

const FilterInput = styled.input`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  font-size: 13px;
  min-width: 150px;
  flex: 1;
  background: ${color.cardBg};

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const FilterSelect = styled.select`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  font-size: 13px;
  min-width: 150px;
  background: ${color.cardBg};

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const Table = styled.table`
  width: 100%;
  border-collapse: collapse;
`

const Th = styled.th`
  text-align: left;
  padding: ${spacing.md};
  background: ${color.primary};
  color: ${color.textInverse};
  font-weight: 500;
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: 0.05em;
  white-space: nowrap;
`

const Td = styled.td`
  padding: ${spacing.md};
  border-bottom: 1px solid ${color.border};
  font-size: 14px;
  color: ${color.text};
`

const Tr = styled.tr<{ $clickable?: boolean }>`
  cursor: ${({ $clickable }) => $clickable ? 'pointer' : 'default'};
  transition: background 0.15s ease;
  
  &:hover {
    background: ${color.backgroundDark};
  }
`

const ActionButton = styled.button<{ $variant?: 'edit' | 'delete' }>`
  background: transparent;
  border: none;
  color: ${color.textMuted};
  font-size: 16px;
  font-weight: 400;
  cursor: pointer;
  padding: ${spacing.xs} ${spacing.sm};
  line-height: 1;
  transition: all 0.2s ease;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  
  &:hover {
    color: ${({ $variant }) => $variant === 'delete' ? color.danger : color.primary};
  }
`

const ActionsCell = styled.td`
  padding: ${spacing.md};
  border-bottom: 1px solid ${color.border};
  text-align: right;
  white-space: nowrap;
`

const EditIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7" />
    <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z" />
  </svg>
)

const DeleteIcon = () => (
  <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
    <polyline points="3 6 5 6 21 6" />
    <path d="M19 6v14a2 2 0 0 1-2 2H7a2 2 0 0 1-2-2V6m3 0V4a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v2" />
    <line x1="10" y1="11" x2="10" y2="17" />
    <line x1="14" y1="11" x2="14" y2="17" />
  </svg>
)

const EmptyState = styled.div`
  padding: ${spacing.xl};
  text-align: center;
  color: ${color.textLight};
`

const LoadingSpinner = styled.div`
  display: inline-block;
  width: 24px;
  height: 24px;
  border: 2px solid ${color.border};
  border-top-color: ${color.primary};
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
  
  @keyframes spin {
    to {
      transform: rotate(360deg);
    }
  }
`

const LoadingContainer = styled.div`
  display: flex;
  justify-content: center;
  align-items: center;
  padding: ${spacing.xl};
`

const TableFooter = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${spacing.md} ${spacing.lg};
  background: ${color.backgroundDark};
  border-top: 1px solid ${color.border};
  font-size: 13px;
  color: ${color.textLight};
`

export type Column<T> = {
  key: keyof T | string
  label: string
  render?: (item: T) => React.ReactNode
  filterable?: boolean
  filterType?: 'text' | 'select'
  filterOptions?: { value: string; label: string }[]
  filterKey?: string
}

type Props<T> = {
  data: T[]
  columns: Column<T>[]
  onView?: (item: T) => void
  onEdit?: (item: T) => void
  onDelete?: (item: T) => void | Promise<void>
  deleteConfirmMessage?: string
  loading?: boolean
  onServerFilter?: (filters: Record<string, string>) => void
  serverFiltering?: boolean
  totalCount?: number
}

function useDebounce<T>(value: T, delay: number): T {
  const [debouncedValue, setDebouncedValue] = useState<T>(value)

  useEffect(() => {
    const handler = setTimeout(() => {
      setDebouncedValue(value)
    }, delay)

    return () => {
      clearTimeout(handler)
    }
  }, [value, delay])

  return debouncedValue
}

function DataTable<T extends { id: number | string }>({
  data,
  columns,
  onView,
  onEdit,
  onDelete,
  deleteConfirmMessage = 'Tem certeza que deseja excluir este item? Essa ação é irreversível.',
  loading = false,
  onServerFilter,
  serverFiltering = false,
  totalCount
}: Props<T>) {
  const [filters, setFilters] = useState<Record<string, string>>({})
  const debouncedFilters = useDebounce(filters, 400)
  const isFirstRender = useRef(true)
  const onServerFilterRef = useRef(onServerFilter)
  onServerFilterRef.current = onServerFilter

  const handleFilterChange = (key: string, value: string) => {
    setFilters((prev) => ({
      ...prev,
      [key]: value
    }))
  }

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false
      return
    }
    if (serverFiltering && onServerFilterRef.current) {
      onServerFilterRef.current(debouncedFilters)
    }
  }, [debouncedFilters, serverFiltering])

  const filteredData = useMemo(() => {
    if (!Array.isArray(data)) return []
    if (serverFiltering) return data
    return data.filter((item) => {
      return Object.entries(filters).every(([key, filterValue]) => {
        if (!filterValue) return true
        const itemValue = String((item as Record<string, unknown>)[key] || '').toLowerCase()
        const col = columns.find(c => String(c.key) === key)
        if (col?.filterType === 'select') {
          return itemValue === filterValue.toLowerCase()
        }
        return itemValue.includes(filterValue.toLowerCase())
      })
    })
  }, [data, filters, columns, serverFiltering])

  const handleDeleteClick = async (e: React.MouseEvent, item: T) => {
    e.stopPropagation()
    
    const result = await swal.fire({
      title: 'Confirmar Exclusão',
      text: deleteConfirmMessage,
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: color.danger,
      cancelButtonColor: color.textLight,
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed && onDelete) {
      try {
        await onDelete(item)
      } catch (error) {
        console.error('Delete operation failed:', error)
      }
    }
  }

  const handleRowClick = (item: T) => {
    if (onView) {
      onView(item)
    }
  }

  const filterableColumns = columns.filter((col) => col.filterable)

  const displayCount = serverFiltering && totalCount !== undefined ? totalCount : filteredData.length

  return (
    <TableWrapper>
      {filterableColumns.length > 0 && (
        <FiltersContainer>
          {filterableColumns.map((col) => {
            const filterKey = col.filterKey || String(col.key)
            return col.filterType === 'select' ? (
              <FilterSelect
                key={filterKey}
                value={filters[filterKey] || ''}
                onChange={(e) => handleFilterChange(filterKey, e.target.value)}
              >
                <option value="">Todos - {col.label}</option>
                {col.filterOptions?.map((opt) => (
                  <option key={opt.value} value={opt.value}>
                    {opt.label}
                  </option>
                ))}
              </FilterSelect>
            ) : (
              <FilterInput
                key={filterKey}
                placeholder={`Filtrar por ${col.label.toLowerCase()}...`}
                value={filters[filterKey] || ''}
                onChange={(e) => handleFilterChange(filterKey, e.target.value)}
              />
            )
          })}
        </FiltersContainer>
      )}

      <div style={{ overflowX: 'auto' }}>
        <Table>
          <thead>
            <tr>
              {columns.map((col) => (
                <Th key={String(col.key)}>{col.label}</Th>
              ))}
              {(onEdit || onDelete) && <Th style={{ width: '80px' }}></Th>}
            </tr>
          </thead>
          <tbody>
            {loading ? (
              <TableSkeleton 
                rows={5} 
                columns={columns.length} 
                hasActions={!!(onEdit || onDelete)} 
              />
            ) : filteredData.length === 0 ? (
              <tr>
                <Td colSpan={columns.length + ((onEdit || onDelete) ? 1 : 0)}>
                  <EmptyState>Nenhum registro encontrado</EmptyState>
                </Td>
              </tr>
            ) : (
              filteredData.map((item) => (
                <Tr 
                  key={item.id} 
                  $clickable={!!onView}
                  onClick={() => handleRowClick(item)}
                >
                  {columns.map((col) => (
                    <Td key={String(col.key)}>
                      {col.render
                        ? col.render(item)
                        : String((item as Record<string, unknown>)[String(col.key)] ?? '')}
                    </Td>
                  ))}
                  {(onEdit || onDelete) && (
                    <ActionsCell>
                      {onEdit && (
                        <ActionButton 
                          $variant="edit"
                          onClick={(e) => { e.stopPropagation(); onEdit(item); }}
                          title="Editar"
                        >
                          <EditIcon />
                        </ActionButton>
                      )}
                      {onDelete && (
                        <ActionButton 
                          $variant="delete"
                          onClick={(e) => handleDeleteClick(e, item)}
                          title="Excluir"
                        >
                          <DeleteIcon />
                        </ActionButton>
                      )}
                    </ActionsCell>
                  )}
                </Tr>
              ))
            )}
          </tbody>
        </Table>
      </div>

      <TableFooter>
        <span>{displayCount} registro(s) encontrado(s)</span>
      </TableFooter>
    </TableWrapper>
  )
}

export default DataTable
