import { useState, useContext, useEffect } from 'react'
import styled from 'styled-components'
import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
import { CondominioType } from '../../pages/Condominios'
import { fetchCepData, formatCep } from '../../utils/cepLookup'

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

const CepHint = styled.span`
  font-size: 12px;
  color: ${color.textLight};
  margin-top: 2px;
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

type Props = {
  onSuccess: () => void
  onClose: () => void
  initialData?: CondominioType | null
}

const CondominioForm = ({ onSuccess, onClose, initialData }: Props) => {
  const api = useAxios()
  const { authTokens } = useContext(AuthContext)
  
  let user_id = ''
  if (authTokens?.access) {
    const decoded: { user_id: string } = jwtDecode(authTokens.access)
    user_id = decoded.user_id
  }

  const [loading, setLoading] = useState(false)
  const [cepLoading, setCepLoading] = useState(false)
  const [nome, setNome] = useState('')
  const [cep, setCep] = useState('')
  const [estado, setEstado] = useState('')
  const [cidade, setCidade] = useState('')
  const [bairro, setBairro] = useState('')
  const [endereco, setEndereco] = useState('')
  const [numero, setNumero] = useState('')
  const [km, setKm] = useState('')
  const [valor, setValor] = useState('')

  const isEditing = !!initialData

  useEffect(() => {
    if (initialData) {
      setNome(initialData.nome || '')
      setCep(initialData.cep || '')
      setEstado(initialData.estado || '')
      setCidade(initialData.cidade || '')
      setBairro(initialData.bairro || '')
      setEndereco(initialData.endereco || '')
      setNumero(String(initialData.numero || ''))
      setKm(String(initialData.km || ''))
      setValor(String(initialData.valor_condominio || ''))
    } else {
      setNome('')
      setCep('')
      setEstado('')
      setCidade('')
      setBairro('')
      setEndereco('')
      setNumero('')
      setKm('')
      setValor('')
    }
  }, [initialData])

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
    
    if (!user_id) {
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
      const data = {
        criado_por: user_id,
        nome,
        cep: cep.replace(/\D/g, ''),
        estado,
        cidade,
        bairro,
        endereco,
        numero: Number(numero) || 0,
        km: Number(km) || 0,
        valor_condominio: Number(valor) || 0
      }

      if (isEditing) {
        await api.put(`/condominio/${initialData.id}/`, data)
        swal.fire({
          title: 'Condomínio atualizado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      } else {
        await api.post('/condominio/', data)
        swal.fire({
          title: 'Condomínio cadastrado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      }

      onSuccess()
      onClose()
    } catch {
      swal.fire({
        title: isEditing ? 'Erro ao atualizar' : 'Erro ao cadastrar',
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
      <FormField>
        <Label>Nome do Condomínio</Label>
        <Input
          type="text"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          required
        />
      </FormField>

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
          <CepHint>Digite o CEP para preencher o endereço automaticamente</CepHint>
        </FormField>
        <FormField>
          <Label>Estado</Label>
          <Input
            type="text"
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
          />
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Cidade</Label>
          <Input
            type="text"
            value={cidade}
            onChange={(e) => setCidade(e.target.value)}
          />
        </FormField>
        <FormField>
          <Label>Bairro</Label>
          <Input
            type="text"
            value={bairro}
            onChange={(e) => setBairro(e.target.value)}
          />
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Endereço</Label>
          <Input
            type="text"
            value={endereco}
            onChange={(e) => setEndereco(e.target.value)}
          />
        </FormField>
        <FormField>
          <Label>Número</Label>
          <Input
            type="number"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
          />
        </FormField>
      </FormRow>

      <FormRow>
        <FormField>
          <Label>Km</Label>
          <Input
            type="number"
            value={km}
            onChange={(e) => setKm(e.target.value)}
          />
        </FormField>
        <FormField>
          <Label>Valor do Condomínio</Label>
          <Input
            type="number"
            value={valor}
            onChange={(e) => setValor(e.target.value)}
          />
        </FormField>
      </FormRow>

      <Button type="submit" disabled={loading}>
        {loading ? (isEditing ? 'Atualizando...' : 'Cadastrando...') : (isEditing ? 'Atualizar Condomínio' : 'Cadastrar Condomínio')}
      </Button>
    </Form>
  )
}

export default CondominioForm
