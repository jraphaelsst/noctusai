import { useState, useContext, useEffect } from 'react'
import styled from 'styled-components'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
import { fetchCepData, formatCep } from '../../utils/cepLookup'
import CorretorAutocomplete from '../CorretorAutocomplete'
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

const Select = styled.select`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  font-size: 14px;
  background: white;
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
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s ease;
  margin-top: ${spacing.md};

  &:hover {
    background: ${color.primaryDark};
  }

  &:disabled {
    background: ${color.textMuted};
    cursor: not-allowed;
  }
`

type PermutaImovelType = {
  id: number
  ref: string | null
  proprietario: number
  proprietario_nome: string
  criado_por: number
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  tipo: number | null
  tipo_nome: string | null
  condominio: number | null
  zona: number | null
  zona_nome: string | null
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  numero: string
  valor: number
}

type Props = {
  onSuccess: () => void
  onClose: () => void
  initialData: PermutaImovelType
}

const PermutaImovelEditForm = ({ onSuccess, onClose, initialData }: Props) => {
  const api = useAxios()
  const { user } = useContext(AuthContext)

  const [loading, setLoading] = useState(false)
  const [cepLoading, setCepLoading] = useState(false)

  const [ref, setRef] = useState(initialData.ref ?? '')
  const [corretor, setCorretor] = useState(initialData.corretor ? String(initialData.corretor) : '')
  const [tipoImovel, setTipoImovel] = useState(initialData.tipo ? String(initialData.tipo) : '')
  const [zona, setZona] = useState(initialData.zona ? String(initialData.zona) : '')
  const [cep, setCep] = useState(initialData.cep ?? '')
  const [estado, setEstado] = useState(initialData.estado ?? '')
  const [cidade, setCidade] = useState(initialData.cidade ?? '')
  const [bairro, setBairro] = useState(initialData.bairro ?? '')
  const [endereco, setEndereco] = useState(initialData.endereco ?? '')
  const [numero, setNumero] = useState(initialData.numero ?? '')
  const [valor, setValor] = useState(String(initialData.valor ?? 0))

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
      }
    }
  }

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault()
    
    if (!user) {
      swal.fire({
        title: 'Usuário não autenticado',
        icon: 'error',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })
      return
    }
    
    setLoading(true)

    try {
      const updateData: Record<string, unknown> = {
        ref: ref || null,
        corretor: corretor ? Number(corretor) : null,
        tipo: tipoImovel ? Number(tipoImovel) : null,
        zona: zona ? Number(zona) : null,
        cep: cep.replace(/\D/g, ''),
        estado,
        cidade,
        bairro,
        endereco,
        numero: numero ? Number(numero) : null,
      }
      
      if (valor) {
        updateData.valor = Number(valor)
      }

      await api.patch(`/permuta/imovel/${initialData.id}/`, updateData)

      swal.fire({
        title: 'Permuta atualizada!',
        icon: 'success',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })

      onSuccess()
      onClose()
    } catch {
      swal.fire({
        title: 'Erro ao atualizar',
        icon: 'error',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })
    } finally {
      setLoading(false)
    }
  }

  return (
    <Form onSubmit={handleSubmit}>
      <FormRow>
        <FormField>
          <Label>Referência</Label>
          <Input
            type="text"
            value={ref}
            onChange={(e) => setRef(e.target.value)}
            placeholder="Código de referência"
          />
        </FormField>
        <FormField>
          <Label>Corretor</Label>
          <CorretorAutocomplete
            value={corretor}
            onChange={(id) => setCorretor(id)}
          />
        </FormField>
      </FormRow>
      <FormRow>
        <FormField>
          <Label>Tipo de Imóvel</Label>
          <SelectWithAdd
            type="tipo_imovel"
            value={tipoImovel}
            onChange={(value) => setTipoImovel(value)}
            required
          />
        </FormField>
        <FormField>
          <Label>Zona</Label>
          <SelectWithAdd
            type="zona"
            value={zona}
            onChange={(value) => setZona(value)}
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
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Estado</Label>
          <Input
            type="text"
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
          />
        </FormField>
        <FormField>
          <Label>Cidade</Label>
          <Input
            type="text"
            value={cidade}
            onChange={(e) => setCidade(e.target.value)}
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
          />
        </FormField>
        <FormField>
          <Label>Endereço</Label>
          <Input
            type="text"
            value={endereco}
            onChange={(e) => setEndereco(e.target.value)}
          />
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Número</Label>
          <Input
            type="text"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
          />
        </FormField>
        <FormField>
          <Label>Valor</Label>
          <Input
            type="number"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
            required
          />
        </FormField>
      </FormRow>

      <Button type="submit" disabled={loading}>
        {loading ? 'Salvando...' : 'Salvar Alterações'}
      </Button>
    </Form>
  )
}

export default PermutaImovelEditForm
