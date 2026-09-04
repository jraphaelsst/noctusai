import { useState, useEffect } from 'react'
import styled from 'styled-components'
import { color, spacing, radius } from '../../styles'
import useAxios from '../../utils/useAxios'
import { getCachedData, setCachedData, invalidateCache } from '../../utils/staticDataCache'
import Modal from '../Modal'
import TipoImovelForm from '../ModalForms/TipoImovelForm'
import TipoAutomovelForm from '../ModalForms/TipoAutomovelForm'
import ZonaForm from '../ModalForms/ZonaForm'

const Container = styled.div`
  display: flex;
  gap: ${spacing.xs};
  align-items: flex-start;
`

const SelectWrapper = styled.div`
  flex: 1;
`

const Select = styled.select`
  width: 100%;
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  border-radius: ${radius.md};
  font-size: 14px;
  background: white;
  transition: border-color 0.2s ease;

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

type Option = {
  value: string
  label: string
}

type SelectType = 'tipo_imovel' | 'tipo_automovel' | 'zona'

type Props = {
  type: SelectType
  value: string
  onChange: (value: string, label?: string) => void
  required?: boolean
  placeholder?: string
  showAllOption?: boolean
}

const API_ENDPOINTS: Record<SelectType, string> = {
  tipo_imovel: '/tipo-imovel/',
  tipo_automovel: '/tipo-automovel/',
  zona: '/zona/'
}

const MODAL_TITLES: Record<SelectType, string> = {
  tipo_imovel: 'Novo Tipo de Imóvel',
  tipo_automovel: 'Novo Tipo de Automóvel',
  zona: 'Nova Zona'
}

const ALL_OPTION_LABELS: Record<SelectType, string> = {
  tipo_imovel: 'Todos',
  tipo_automovel: 'Todos',
  zona: 'Todas'
}

const SelectWithAdd = ({ type, value, onChange, required, placeholder = 'Selecione...', showAllOption = false }: Props) => {
  const api = useAxios()
  const [options, setOptions] = useState<Option[]>([])
  const [showModal, setShowModal] = useState(false)
  const [loading, setLoading] = useState(true)

  const fetchOptions = async (forceRefresh = false) => {
    const cacheKey = `selectWithAdd_${type}`
    
    if (!forceRefresh) {
      const cachedOptions = getCachedData<Option[]>(cacheKey)
      if (cachedOptions) {
        setOptions(cachedOptions)
        setLoading(false)
        return
      }
    }
    
    setLoading(true)
    try {
      const response = await api.get(API_ENDPOINTS[type])
      const data = response.data
      const items = data.results ? data.results : (Array.isArray(data) ? data : [])
      const mappedOptions = items.map((item: { id: number; nome: string }) => ({
        value: String(item.id),
        label: item.nome
      }))
      setOptions(mappedOptions)
      setCachedData(cacheKey, mappedOptions)
    } catch (error) {
      console.error(`Error fetching ${type} options:`, error)
      setOptions([])
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    fetchOptions()
  }, [type])

  const handleSuccess = async (newItem: { id: number; nome: string }) => {
    setShowModal(false)
    onChange(String(newItem.id))
    invalidateCache(`selectWithAdd_${type}`)
    await fetchOptions(true)
  }

  const renderForm = () => {
    switch (type) {
      case 'tipo_imovel':
        return (
          <TipoImovelForm
            onSuccess={handleSuccess}
            onClose={() => setShowModal(false)}
          />
        )
      case 'tipo_automovel':
        return (
          <TipoAutomovelForm
            onSuccess={handleSuccess}
            onClose={() => setShowModal(false)}
          />
        )
      case 'zona':
        return (
          <ZonaForm
            onSuccess={handleSuccess}
            onClose={() => setShowModal(false)}
          />
        )
      default:
        return null
    }
  }

  return (
    <>
      <Container>
        <SelectWrapper>
          <Select
            value={value}
            onChange={(e) => {
              const selectedValue = e.target.value
              const selectedOption = options.find(opt => opt.value === selectedValue)
              const label = selectedValue === 'all' ? ALL_OPTION_LABELS[type] : (selectedOption?.label || '')
              onChange(selectedValue, label)
            }}
            required={required}
            disabled={loading}
          >
            <option value="">{loading ? 'Carregando...' : placeholder}</option>
            {showAllOption && (
              <option value="all">{ALL_OPTION_LABELS[type]}</option>
            )}
            {options.map(opt => (
              <option key={opt.value} value={opt.value}>{opt.label}</option>
            ))}
          </Select>
        </SelectWrapper>
        <AddButton type="button" onClick={() => setShowModal(true)} title={`Adicionar ${MODAL_TITLES[type].toLowerCase().replace('novo ', '').replace('nova ', '')}`}>
          +
        </AddButton>
      </Container>

      {showModal && (
        <Modal
          isOpen={showModal}
          onClose={() => setShowModal(false)}
          title={MODAL_TITLES[type]}
        >
          {renderForm()}
        </Modal>
      )}
    </>
  )
}

export default SelectWithAdd
