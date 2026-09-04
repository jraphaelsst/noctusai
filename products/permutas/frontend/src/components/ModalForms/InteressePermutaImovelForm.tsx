import { useState } from 'react'
import styled from 'styled-components'
import { color, radius, spacing } from '../../styles'
import { fetchCepData, formatCep } from '../../utils/cepLookup'
import SelectWithAdd from '../SelectWithAdd'

const Form = styled.form`
  display: flex;
  flex-direction: column;
  gap: ${spacing.md};
`

const FormRow = styled.div`
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: ${spacing.md};

  @media (max-width: 600px) {
    grid-template-columns: 1fr;
  }
`

const FormField = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.xs};
`

const Label = styled.label`
  font-size: 14px;
  font-weight: 500;
  color: ${color.text};
`

const Input = styled.input`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  border-radius: ${radius.md};
  font-size: 14px;
  transition: border-color 0.2s ease;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const CepInputWrapper = styled.div`
  position: relative;
`

const CepInput = styled(Input)<{ $loading?: boolean }>`
  padding-right: ${props => props.$loading ? '40px' : spacing.md};
`

const CepSpinner = styled.div`
  position: absolute;
  right: 12px;
  top: 50%;
  transform: translateY(-50%);
  width: 16px;
  height: 16px;
  border: 2px solid ${color.border};
  border-top-color: ${color.primary};
  border-radius: 50%;
  animation: spin 0.8s linear infinite;

  @keyframes spin {
    to { transform: translateY(-50%) rotate(360deg); }
  }
`

const CepHint = styled.span`
  font-size: 12px;
  color: ${color.textLight};
  margin-top: 2px;
`

const AddressFields = styled.div<{ $visible: boolean }>`
  display: flex;
  flex-direction: column;
  gap: ${spacing.md};
  overflow: hidden;
  max-height: ${props => props.$visible ? '500px' : '0'};
  opacity: ${props => props.$visible ? 1 : 0};
  transform: translateY(${props => props.$visible ? '0' : '-10px'});
  transition: max-height 0.4s ease, opacity 0.3s ease, transform 0.3s ease;
`

const TextArea = styled.textarea`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  border-radius: ${radius.md};
  font-size: 14px;
  resize: vertical;
  min-height: 80px;
  transition: border-color 0.2s ease;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

const Button = styled.button`
  padding: ${spacing.md} ${spacing.lg};
  background: ${color.primary};
  color: ${color.textInverse};
  border: none;
  border-radius: ${radius.md};
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
  margin-top: ${spacing.md};

  &:hover {
    background: ${color.primaryDark};
  }
`

const Description = styled.p`
  font-size: 14px;
  color: ${color.textLight};
  margin-bottom: ${spacing.md};
  padding: ${spacing.sm};
  background: ${color.background};
  border-radius: ${radius.md};
`

export type InteressePermutaImovelData = {
  tipo_imovel: string
  tipo_imovel_nome: string
  zona: string
  zona_nome: string
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  valor_minimo: string
  valor_maximo: string
  observacoes: string
}

type InitialData = {
  tipo_imovel?: number | null
  zona?: number | null
  estado?: string | null
  valor_minimo?: number | null
  valor_maximo?: number | null
  observacoes?: string | null
}

type Props = {
  onAdd: (data: InteressePermutaImovelData) => void
  onClose: () => void
  initialData?: InitialData
}

const InteressePermutaImovelForm = ({ onAdd, onClose, initialData }: Props) => {
  const [tipoImovel, setTipoImovel] = useState(initialData?.tipo_imovel?.toString() || '')
  const [tipoImovelNome, setTipoImovelNome] = useState('')
  const [zona, setZona] = useState(initialData?.zona?.toString() || '')
  const [zonaNome, setZonaNome] = useState('')
  const [cep, setCep] = useState('')
  const [cepLoading, setCepLoading] = useState(false)
  const [addressLoaded, setAddressLoaded] = useState(!!initialData?.estado)
  const [estado, setEstado] = useState(initialData?.estado || '')
  const [cidade, setCidade] = useState('')
  const [bairro, setBairro] = useState('')
  const [endereco, setEndereco] = useState('')
  const [valorMinimo, setValorMinimo] = useState(initialData?.valor_minimo?.toString() || '')
  const [valorMaximo, setValorMaximo] = useState(initialData?.valor_maximo?.toString() || '')
  const [observacoes, setObservacoes] = useState(initialData?.observacoes || '')

  const handleCepChange = async (value: string) => {
    const formattedCep = formatCep(value)
    setCep(formattedCep)

    const cleanCep = value.replace(/\D/g, '')
    if (cleanCep.length === 8) {
      setCepLoading(true)
      const data = await fetchCepData(cleanCep)
      setCepLoading(false)

      if (data) {
        setEstado(data.uf)
        setCidade(data.localidade)
        setBairro(data.bairro)
        setEndereco(data.logradouro)
        setAddressLoaded(true)
      }
    } else {
      setAddressLoaded(false)
    }
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onAdd({
      tipo_imovel: tipoImovel === 'all' ? '' : tipoImovel,
      tipo_imovel_nome: tipoImovel === 'all' ? 'Todos' : tipoImovelNome,
      zona: zona === 'all' ? '' : zona,
      zona_nome: zona === 'all' ? 'Todas' : zonaNome,
      cep: cep.replace(/\D/g, ''),
      estado,
      cidade,
      bairro,
      endereco,
      valor_minimo: valorMinimo,
      valor_maximo: valorMaximo,
      observacoes
    })
    onClose()
  }

  return (
    <>
      <Description>
        Defina que tipo de imóvel o proprietário desta permuta aceita em troca. 
        Para que um match bilateral seja criado, ambos os lados precisam ter interesses compatíveis.
      </Description>
      <Form onSubmit={handleSubmit}>
        <FormRow>
          <FormField>
            <Label>Tipo de Imóvel Desejado</Label>
            <SelectWithAdd
              type="tipo_imovel"
              value={tipoImovel}
              onChange={(value, label) => {
                setTipoImovel(value)
                setTipoImovelNome(label || '')
              }}
              showAllOption
            />
          </FormField>
          <FormField>
            <Label>Zona Desejada</Label>
            <SelectWithAdd
              type="zona"
              value={zona}
              onChange={(value, label) => {
                setZona(value)
                setZonaNome(label || '')
              }}
              showAllOption
            />
          </FormField>
        </FormRow>

        <FormRow>
          <FormField>
            <Label>CEP</Label>
            <CepInputWrapper>
              <CepInput
                type="text"
                value={cep}
                onChange={(e) => handleCepChange(e.target.value)}
                placeholder="00000-000"
                maxLength={9}
                $loading={cepLoading}
              />
              {cepLoading && <CepSpinner />}
            </CepInputWrapper>
            <CepHint>Digite o CEP para preencher automaticamente</CepHint>
          </FormField>
        </FormRow>

        <AddressFields $visible={addressLoaded}>
          <FormRow>
            <FormField>
              <Label>Estado</Label>
              <Input
                type="text"
                value={estado}
                onChange={(e) => setEstado(e.target.value)}
                placeholder="Ex: SP, RJ, MG..."
              />
            </FormField>
            <FormField>
              <Label>Cidade</Label>
              <Input
                type="text"
                value={cidade}
                onChange={(e) => setCidade(e.target.value)}
                placeholder="Ex: São Paulo"
              />
            </FormField>
          </FormRow>

          <FormRow>
            <FormField>
              <Label>Bairro</Label>
              <Input
                type="text"
                value={bairro}
                onChange={(e) => setBairro(e.target.value)}
                placeholder="Ex: Centro"
              />
            </FormField>
            <FormField>
              <Label>Endereço</Label>
              <Input
                type="text"
                value={endereco}
                onChange={(e) => setEndereco(e.target.value)}
                placeholder="Ex: Rua das Flores"
              />
            </FormField>
          </FormRow>
        </AddressFields>

        <FormRow>
          <FormField>
            <Label>Valor Mínimo Aceito</Label>
            <Input
              type="number"
              value={valorMinimo}
              onChange={(e) => setValorMinimo(e.target.value)}
              placeholder="Ex: 300000"
            />
          </FormField>
          <FormField>
            <Label>Valor Máximo Aceito</Label>
            <Input
              type="number"
              value={valorMaximo}
              onChange={(e) => setValorMaximo(e.target.value)}
              placeholder="Ex: 500000"
            />
          </FormField>
        </FormRow>

        <FormField>
          <Label>Observações</Label>
          <TextArea
            value={observacoes}
            onChange={(e) => setObservacoes(e.target.value)}
            placeholder="Informações adicionais..."
          />
        </FormField>

        <Button type="submit">Adicionar Interesse</Button>
      </Form>

    </>
  )
}

export default InteressePermutaImovelForm
