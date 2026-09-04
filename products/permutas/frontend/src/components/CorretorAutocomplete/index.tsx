import { useState, useEffect, useRef } from 'react'
import styled from 'styled-components'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import Modal from '../Modal'
import CorretorForm from '../ModalForms/CorretorForm'

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

const SuggestionDetails = styled.div`
  font-size: 12px;
  color: ${color.textMuted};
  margin-top: 2px;
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

export type Corretor = {
  id: number
  nome: string
  telefone: string
  email: string
  creci: string
}

type Props = {
  value: string
  onChange: (id: string, corretor?: Corretor) => void
  required?: boolean
  showAddButton?: boolean
}

const CorretorAutocomplete = ({ value, onChange, required, showAddButton = true }: Props) => {
  const api = useAxios()
  const [query, setQuery] = useState('')
  const [suggestions, setSuggestions] = useState<Corretor[]>([])
  const [showSuggestions, setShowSuggestions] = useState(false)
  const [loading, setLoading] = useState(false)
  const [selectedCorretor, setSelectedCorretor] = useState<Corretor | null>(null)
  const [highlightedIndex, setHighlightedIndex] = useState(-1)
  const [showModal, setShowModal] = useState(false)
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
    if (value && !selectedCorretor) {
      api.get(`/corretor/${value}/`)
        .then(res => {
          setSelectedCorretor(res.data)
        })
        .catch(() => {})
    }
  }, [value])

  useEffect(() => {
    if (query.length < 2) {
      setSuggestions([])
      return
    }

    const searchTimeout = setTimeout(async () => {
      setLoading(true)
      try {
        const res = await api.get(`/corretor/?search=${encodeURIComponent(query)}`)
        const data = res.data
        const items = data.results ? data.results : (Array.isArray(data) ? data : [])
        setSuggestions(items)
        setShowSuggestions(true)
        setHighlightedIndex(-1)
      } catch (error) {
        console.error('Error searching corretores:', error)
        setSuggestions([])
      } finally {
        setLoading(false)
      }
    }, 300)

    return () => clearTimeout(searchTimeout)
  }, [query])

  const handleSelect = (corretor: Corretor) => {
    setSelectedCorretor(corretor)
    onChange(String(corretor.id), corretor)
    setQuery('')
    setShowSuggestions(false)
    setSuggestions([])
  }

  const handleClear = () => {
    setSelectedCorretor(null)
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

  const handleAddSuccess = (newCorretor: Corretor) => {
    setShowModal(false)
    handleSelect(newCorretor)
  }

  if (selectedCorretor) {
    return (
      <Container ref={containerRef}>
        <SelectedBadge>
          <SelectedText>
            {selectedCorretor.nome}
            {selectedCorretor.creci && ` - CRECI: ${selectedCorretor.creci}`}
          </SelectedText>
          <ClearButton type="button" onClick={handleClear}>×</ClearButton>
        </SelectedBadge>
        {showAddButton && (
          <AddButton type="button" onClick={() => setShowModal(true)} title="Adicionar novo corretor">+</AddButton>
        )}
        <input type="hidden" value={value} required={required} />
        
        <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Novo Corretor">
          <CorretorForm onSuccess={handleAddSuccess} onClose={() => setShowModal(false)} />
        </Modal>
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
          onFocus={() => query.length >= 2 && setShowSuggestions(true)}
          onKeyDown={handleKeyDown}
          placeholder="Digite nome, email ou CRECI..."
          required={required && !value}
        />
        <SuggestionsList $show={showSuggestions && query.length >= 2}>
          {loading ? (
            <NoResults>Buscando...</NoResults>
          ) : suggestions.length > 0 ? (
            suggestions.map((corr, index) => (
              <SuggestionItem
                key={corr.id}
                onClick={() => handleSelect(corr)}
                $highlighted={index === highlightedIndex}
              >
                <SuggestionName>{corr.nome}</SuggestionName>
                <SuggestionDetails>
                  {corr.creci && `CRECI: ${corr.creci}`}
                  {corr.creci && corr.telefone && ' | '}
                  {corr.telefone && `Tel: ${corr.telefone}`}
                </SuggestionDetails>
              </SuggestionItem>
            ))
          ) : (
            <NoResults>Nenhum corretor encontrado</NoResults>
          )}
        </SuggestionsList>
      </InputWrapper>
      {showAddButton && (
        <AddButton type="button" onClick={() => setShowModal(true)} title="Adicionar novo corretor">+</AddButton>
      )}
      
      <Modal isOpen={showModal} onClose={() => setShowModal(false)} title="Novo Corretor">
        <CorretorForm onSuccess={handleAddSuccess} onClose={() => setShowModal(false)} />
      </Modal>
    </Container>
  )
}

export default CorretorAutocomplete
