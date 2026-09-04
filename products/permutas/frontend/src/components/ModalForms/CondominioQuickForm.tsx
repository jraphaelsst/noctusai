import { useState, useContext } from 'react'
import styled from 'styled-components'
import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
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
  color: ${color.textMuted};
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
  onSuccess: (newCondominio: { id: number; nome: string; bairro: string; cidade: string; estado: string }) => void
  onClose: () => void
}

const CondominioQuickForm = ({ onSuccess, onClose }: Props) => {
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
  const [valorCondominio, setValorCondominio] = useState('')

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
      const payload: Record<string, unknown> = {
        criado_por: Number(user_id),
        nome
      }
      
      if (cep) payload.cep = cep.replace(/\D/g, '')
      if (estado) payload.estado = estado
      if (cidade) payload.cidade = cidade
      if (bairro) payload.bairro = bairro
      if (endereco) payload.endereco = endereco
      if (numero) payload.numero = Number(numero)
      if (km) payload.km = Number(km)
      if (valorCondominio) payload.valor_condominio = Number(valorCondominio)
      
      const response = await api.post('/condominio/', payload)

      swal.fire({
        title: 'Condomínio cadastrado!',
        icon: 'success',
        toast: true,
        timer: 3000,
        position: 'top-right',
        timerProgressBar: true,
        showConfirmButton: false
      })

      onSuccess(response.data)
      onClose()
    } catch {
      swal.fire({
        title: 'Erro ao cadastrar',
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
        <Label>Nome do Condomínio *</Label>
        <Input
          type="text"
          value={nome}
          onChange={(e) => setNome(e.target.value)}
          placeholder="Nome do condomínio"
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
          <CepHint>Digite o CEP para preencher automaticamente</CepHint>
        </FormField>
        <FormField>
          <Label>Estado</Label>
          <Input
            type="text"
            value={estado}
            onChange={(e) => setEstado(e.target.value)}
            placeholder="UF"
            maxLength={2}
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
            placeholder="Cidade"
          />
        </FormField>
        <FormField>
          <Label>Bairro</Label>
          <Input
            type="text"
            value={bairro}
            onChange={(e) => setBairro(e.target.value)}
            placeholder="Bairro"
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
            placeholder="Rua, Avenida..."
          />
        </FormField>
        <FormField>
          <Label>Número</Label>
          <Input
            type="number"
            value={numero}
            onChange={(e) => setNumero(e.target.value)}
            placeholder="Nº"
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
            placeholder="Distância em Km"
          />
        </FormField>
        <FormField>
          <Label>Valor do Condomínio (R$)</Label>
          <Input
            type="number"
            value={valorCondominio}
            onChange={(e) => setValorCondominio(e.target.value)}
            placeholder="0"
          />
        </FormField>
      </FormRow>

      <Button type="submit" disabled={loading}>
        {loading ? 'Cadastrando...' : 'Cadastrar Condomínio'}
      </Button>
    </Form>
  )
}

export default CondominioQuickForm
