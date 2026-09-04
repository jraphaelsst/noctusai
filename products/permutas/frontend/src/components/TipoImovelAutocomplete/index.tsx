import { useState, useEffect, useRef } from 'react'
import styled from 'styled-components'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'

const Container = styled.div`
  position: relative;
  width: 100%;
  display: flex;
  gap: ${spacing.xs};
  align-items: flex-start;
`

const InputWrapper = styled.div`
  position: relative;
  flex: 1;
`

const Input = styled.input`
  width: 100%;
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  font-size: 14px;
  transition: border-color 0.2s ease;
  box-sizing: border-box;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const AddButton = styled.button`
  padding: ${spacing.sm};
  background: ${color.primary};
  color: ${color.textInverse};
  border: none;
  width: 36px;
  height: 36px;
  display: flex;
  align-items: center;
  justify-content: center;
  cursor: pointer;
  transition: background 0.2s ease;
  font-size: 18px;
  font-weight: bold;

  &:hover {
    background: ${color.primaryDark};
  }
`

const SuggestionsList = styled.div<{ $show: boolean }>`
  position: absolute;
  top: 100%;
  left: 0;
  right: 0;
  background: white;
  border: 1px solid ${color.border};
  border-top: none;
  max-height: 200px;
  overflow-y: auto;
  z-index: 1000;
  display: ${props => props.$show ? 'block' : 'none'};
  box-shadow: 0 4px 12px rgba(0, 0, 0, 0.1);
`

const SuggestionItem = styled.div<{ $highlighted?: boolean }>`
  padding: ${spacing.sm} ${spacing.md};
  cursor: pointer;
  background: ${props => props.$highlighted ? color.background : 'white'};
  border-bottom: 1px solid ${color.border};
  transition: background 0.15s ease;

  &:last-child {
    border-bottom: none;
  }

  &:hover {
    background: ${color.background};
  }
`

const SuggestionName = styled.div`
  font-weight: 500;
  color: ${color.text};
  font-size: 14px;
`

const NoResults = styled.div`
  padding: ${spacing.sm} ${spacing.md};
  color: ${color.textMuted};
  font-size: 14px;
  text-align: center;
`

const SelectedBadge = styled.div`
  display: flex;
  align-items: center;
  gap: ${spacing.sm};
  padding: ${spacing.sm} ${spacing.md};
  background: ${color.background};
  border: 1px solid ${color.primary};
  flex: 1;
`

const SelectedText = styled.span`
  flex: 1;
  font-size: 14px;
  color: ${color.text};
`

const ClearButton = styled.button`
  background: none;
  border: none;
  color: ${color.textMuted};
  cursor: pointer;
  font-size: 18px;
  padding: 0 4px;
  line-height: 1;

  &:hover {
    color: ${color.text};
  }
`

export type TipoImovel = {
  id: number
  nome: string
}

type Props = {
  value: string
  onChange: (id: string, tipo?: TipoImovel) => void
  onAddClick?: () => void
  required?: boolean
  showAddButton?: boolean
}

const TipoImovelAutocomplete = ({ value, onChange, onAddClick, required, showAddButton = true }: Props) => {
  const api = useAxios()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<TipoImovel[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selectedTipo, setSelectedTipo] = useState<TipoImovel | null>(null)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const containerRef = useRef<HTMLDivElement>(null)
  const inputRef = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) {
        setShowSuggestions(false)
      }
    }

    document.addEventListener('mousedown', handleClickOutside)
    return () => document.removeEventListener('mousedown', handleClickOutside)
  }, [])

  useEffect(() => {
    if (value && !selectedTipo) {
      api.get(`/tipo-imovel/${value}/`)
        .then(res => {
          setSelectedTipo(res.data)
        })
        .catch(() => {})
    }
  }, [value])

  useEffect(() => {
    const searchTimeout = setTimeout(async () => {
      setLoading(true)
      try {
        const searchParam = query.length >= 1 ? `?search=${encodeURIComponent(query)}` : ''
        const res = await api.get(`/tipo-imovel/${searchParam}`)
        const data = res.data
        const items = data.results ? data.results : (Array.isArray(data) ? data : [])
        setSuggestions(items)
        setShowSuggestions(true)
        setHighlightedIndex(-1)
      } catch (error) {
        console.error('Error searching tipos:', error)
        setSuggestions([])
      } finally {
        setLoading(false)
      }
    }, 300)

    return () => clearTimeout(searchTimeout)
  }, [query])

  const handleSelect = (tipo: TipoImovel) => {
    setSelectedTipo(tipo)
    onChange(String(tipo.id), tipo)
    setQuery('')
    setShowSuggestions(false)
    setSuggestions([])
  }

  const handleClear = () => {
    setSelectedTipo(null)
    onChange('')
    setQuery('')
    inputRef.current?.focus()
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (!showSuggestions || suggestions.length === 0) return

    if (e.key === 'ArrowDown') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.min(prev + 1, suggestions.length - 1))
    } else if (e.key === 'ArrowUp') {
      e.preventDefault()
      setHighlightedIndex(prev => Math.max(prev - 1, 0))
    } else if (e.key === 'Enter' && highlightedIndex >= 0) {
      e.preventDefault()
      handleSelect(suggestions[highlightedIndex])
    } else if (e.key === 'Escape') {
      setShowSuggestions(false)
    }
  }

  const handleFocus = async () => {
    setLoading(true)
    try {
      const res = await api.get('/tipo-imovel/')
      const data = res.data
      const items = data.results ? data.results : (Array.isArray(data) ? data : [])
      setSuggestions(items)
      setShowSuggestions(true)
    } catch (error) {
      console.error('Error loading tipos:', error)
    } finally {
      setLoading(false)
    }
  }

  if (selectedTipo) {
    return (
      <Container ref={containerRef}>
        <SelectedBadge>
          <SelectedText>{selectedTipo.nome}</SelectedText>
          <ClearButton type="button" onClick={handleClear}>×</ClearButton>
        </SelectedBadge>
        {showAddButton && onAddClick && (
          <AddButton type="button" onClick={onAddClick} title="Adicionar novo tipo">+</AddButton>
        )}
        <input type="hidden" value={value} required={required} />
      </Container>
    )
  }

  return (
    <Container ref={containerRef}>
      <InputWrapper>
        <Input
          ref={inputRef}
          type="text"
          value={query}
          onChange={(e) => setQuery(e.target.value)}
          onFocus={handleFocus}
          onKeyDown={handleKeyDown}
          placeholder="Digite para buscar ou selecione..."
          required={required && !value}
        />
        <SuggestionsList $show={showSuggestions}>
          {loading ? (
            <NoResults>Buscando...</NoResults>
          ) : suggestions.length > 0 ? (
            suggestions.map((tipo, index) => (
              <SuggestionItem
                key={tipo.id}
                onClick={() => handleSelect(tipo)}
                $highlighted={index === highlightedIndex}
              >
                <SuggestionName>{tipo.nome}</SuggestionName>
              </SuggestionItem>
            ))
          ) : (
            <NoResults>Nenhum tipo encontrado</NoResults>
          )}
        </SuggestionsList>
      </InputWrapper>
      {showAddButton && onAddClick && (
        <AddButton type="button" onClick={onAddClick} title="Adicionar novo tipo">+</AddButton>
      )}
    </Container>
  )
}

export default TipoImovelAutocomplete
