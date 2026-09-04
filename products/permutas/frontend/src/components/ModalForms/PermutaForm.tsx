import { useState, useContext } from 'react'
import styled from 'styled-components'
import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { color, spacing, radius } from '../../styles'
import AuthContext from '../../context/AuthContext'
import ProprietarioAutocomplete from '../ProprietarioAutocomplete'
import CorretorAutocomplete from '../CorretorAutocomplete'
import Modal from '../Modal'
import ProprietarioForm from './ProprietarioForm'
import { fetchCepData, formatCep } from '../../utils/cepLookup'
import SelectWithAdd from '../SelectWithAdd'
import InteressePermutaImovelForm, { InteressePermutaImovelData } from './InteressePermutaImovelForm'
import InteressePermutaAutomovelForm, { InteressePermutaAutomovelData } from './InteressePermutaAutomovelForm'
import { DeleteIcon } from '../Icons'

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

const TabContainer = styled.div`
  display: flex;
  gap: ${spacing.sm};
  margin-bottom: ${spacing.md};
`

const Tab = styled.button<{ $active: boolean }>`
  padding: ${spacing.sm} ${spacing.lg};
  background: ${(props) => (props.$active ? color.primary : color.border)};
  color: ${(props) => (props.$active ? color.textInverse : color.text)};
  border: none;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: ${(props) => (props.$active ? color.primaryDark : color.textMuted)};
  }
`

const InteresseSection = styled.div`
  margin-top: ${spacing.lg};
  padding: ${spacing.md};
  background: ${color.background};
  border-radius: ${radius.md};
  border: 1px solid ${color.border};
`

const InteresseSectionHeader = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: ${spacing.md};
`

const InteresseSectionTitle = styled.h4`
  font-size: 14px;
  font-weight: 600;
  color: ${color.text};
  margin: 0;
`

const AddInteresseButton = styled.button`
  padding: ${spacing.xs} ${spacing.md};
  background: ${color.success};
  color: white;
  border: none;
  border-radius: ${radius.sm};
  font-size: 12px;
  font-weight: 500;
  cursor: pointer;
  transition: background 0.2s ease;

  &:hover {
    opacity: 0.9;
  }
`

const InteresseList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.sm};
`

const InteresseItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${spacing.sm} ${spacing.md};
  background: white;
  border: 1px solid ${color.border};
  border-radius: ${radius.sm};
`

const InteresseInfo = styled.div`
  display: flex;
  flex-direction: column;
  gap: 2px;
`

const InteresseText = styled.span`
  font-size: 13px;
  color: ${color.text};
`

const InteresseSubtext = styled.span`
  font-size: 11px;
  color: ${color.textLight};
`

const DeleteInteresseButton = styled.button`
  background: none;
  border: none;
  cursor: pointer;
  padding: 4px;
  display: flex;
  align-items: center;
  color: ${color.danger};

  &:hover {
    opacity: 0.7;
  }
`

const EmptyInteresses = styled.p`
  font-size: 13px;
  color: ${color.textLight};
  text-align: center;
  margin: ${spacing.md} 0;
`

type Props = {
  onSuccess: () => void
  onClose: () => void
}

const PermutaForm = ({ onSuccess, onClose }: Props) => {
  const api = useAxios()
  const { authTokens } = useContext(AuthContext)
  
  let user_id = ''
  if (authTokens?.access) {
    const decoded: { user_id: string } = jwtDecode(authTokens.access)
    user_id = decoded.user_id
  }

  const [loading, setLoading] = useState(false)
  const [cepLoading, setCepLoading] = useState(false)
  const [addressLoaded, setAddressLoaded] = useState(false)
  const [tipoPermuta, setTipoPermuta] = useState<'imovel' | 'automovel'>('imovel')
  const [proprietarioModalOpen, setProprietarioModalOpen] = useState(false)
  const [interesseModalOpen, setInteresseModalOpen] = useState(false)
  const [interessesImovel, setInteressesImovel] = useState<InteressePermutaImovelData[]>([])
  const [interessesAutomovel, setInteressesAutomovel] = useState<InteressePermutaAutomovelData[]>([])

  const [proprietario, setProprietario] = useState('')
  const [corretor, setCorretor] = useState('')

  const [ref, setRef] = useState('')
  const [tipoImovel, setTipoImovel] = useState('')
  const [zona, setZona] = useState('')
  const [cep, setCep] = useState('')
  const [estado, setEstado] = useState('')
  const [cidade, setCidade] = useState('')
  const [bairro, setBairro] = useState('')
  const [endereco, setEndereco] = useState('')
  const [valorImovel, setValorImovel] = useState('')

  const [tipoAutomovel, setTipoAutomovel] = useState('')
  const [marca, setMarca] = useState('')
  const [modelo, setModelo] = useState('')
  const [motor, setMotor] = useState('')
  const [valorAutomovel, setValorAutomovel] = useState('')

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

  const handleAddInteresseImovel = (data: InteressePermutaImovelData) => {
    setInteressesImovel([...interessesImovel, data])
    setInteresseModalOpen(false)
  }

  const handleAddInteresseAutomovel = (data: InteressePermutaAutomovelData) => {
    setInteressesAutomovel([...interessesAutomovel, data])
    setInteresseModalOpen(false)
  }

  const handleRemoveInteresseImovel = (index: number) => {
    setInteressesImovel(interessesImovel.filter((_, i) => i !== index))
  }

  const handleRemoveInteresseAutomovel = (index: number) => {
    setInteressesAutomovel(interessesAutomovel.filter((_, i) => i !== index))
  }

  const formatCurrencyDisplay = (value: string) => {
    if (!value) return '-'
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(Number(value))
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
      if (tipoPermuta === 'imovel') {
        const response = await api.post('/permuta/imovel/', {
          proprietario: Number(proprietario),
          corretor: corretor ? Number(corretor) : null,
          ref: ref || null,
          tipo: tipoImovel ? Number(tipoImovel) : null,
          zona: zona ? Number(zona) : null,
          cep: cep.replace(/\D/g, ''),
          estado,
          cidade,
          bairro,
          endereco,
          valor: Number(valorImovel)
        })
        
        const permutaId = response.data.id
        for (const interesse of interessesImovel) {
          await api.post('/permuta/interesse-imovel/', {
            permuta_imovel: permutaId,
            tipo_imovel: interesse.tipo_imovel ? Number(interesse.tipo_imovel) : null,
            zona: interesse.zona ? Number(interesse.zona) : null,
            cep: interesse.cep,
            estado: interesse.estado,
            cidade: interesse.cidade,
            bairro: interesse.bairro,
            endereco: interesse.endereco,
            valor_minimo: interesse.valor_minimo ? Number(interesse.valor_minimo) : null,
            valor_maximo: interesse.valor_maximo ? Number(interesse.valor_maximo) : null,
            observacoes: interesse.observacoes
          })
        }
      } else {
        const response = await api.post('/permuta/automovel/', {
          proprietario: Number(proprietario),
          corretor: corretor ? Number(corretor) : null,
          tipo: tipoAutomovel ? Number(tipoAutomovel) : null,
          marca,
          modelo,
          motor,
          valor: Number(valorAutomovel)
        })
        
        const permutaId = response.data.id
        for (const interesse of interessesAutomovel) {
          await api.post('/permuta/interesse-automovel/', {
            permuta_automovel: permutaId,
            tipo_imovel: interesse.tipo_imovel ? Number(interesse.tipo_imovel) : null,
            zona: interesse.zona ? Number(interesse.zona) : null,
            cep: interesse.cep,
            estado: interesse.estado,
            cidade: interesse.cidade,
            bairro: interesse.bairro,
            endereco: interesse.endereco,
            valor_minimo: interesse.valor_minimo ? Number(interesse.valor_minimo) : null,
            valor_maximo: interesse.valor_maximo ? Number(interesse.valor_maximo) : null,
            observacoes: interesse.observacoes
          })
        }
      }

      swal.fire({
        title: 'Permuta cadastrada!',
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
    <>
    <Form onSubmit={handleSubmit}>
      <TabContainer>
        <Tab
          type="button"
          $active={tipoPermuta === 'imovel'}
          onClick={() => setTipoPermuta('imovel')}
        >
          Imóvel
        </Tab>
        <Tab
          type="button"
          $active={tipoPermuta === 'automovel'}
          onClick={() => setTipoPermuta('automovel')}
        >
          Automóvel
        </Tab>
      </TabContainer>

      <FormRow>
        <FormField>
          <Label>Proprietário</Label>
          <ProprietarioAutocomplete
            value={proprietario}
            onChange={(id) => setProprietario(id)}
            onAddClick={() => setProprietarioModalOpen(true)}
            required
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

      {tipoPermuta === 'imovel' ? (
        <>
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
              <Label>Tipo de Imóvel</Label>
              <SelectWithAdd
                type="tipo_imovel"
                value={tipoImovel}
                onChange={(value) => setTipoImovel(value)}
                required
              />
            </FormField>
          </FormRow>
          <FormRow>
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
          </AddressFields>
          <FormRow>
            <FormField>
              <Label>Valor</Label>
              <Input
                type="number"
                value={valorImovel}
                onChange={(e) => setValorImovel(e.target.value)}
                required
              />
            </FormField>
          </FormRow>

          <InteresseSection>
            <InteresseSectionHeader>
              <InteresseSectionTitle>O que aceita em troca?</InteresseSectionTitle>
              <AddInteresseButton type="button" onClick={() => setInteresseModalOpen(true)}>
                + Adicionar Interesse
              </AddInteresseButton>
            </InteresseSectionHeader>
            {interessesImovel.length > 0 ? (
              <InteresseList>
                {interessesImovel.map((interesse, index) => (
                  <InteresseItem key={index}>
                    <InteresseInfo>
                      <InteresseText>
                        {interesse.tipo_imovel ? `Tipo: ${interesse.tipo_imovel_nome || interesse.tipo_imovel}` : 'Qualquer tipo'}
                        {interesse.zona ? ` | Zona: ${interesse.zona_nome || interesse.zona}` : ''}
                        {interesse.estado ? ` | ${interesse.estado}` : ''}
                      </InteresseText>
                      <InteresseSubtext>
                        {interesse.valor_minimo || interesse.valor_maximo
                          ? `${formatCurrencyDisplay(interesse.valor_minimo)} - ${formatCurrencyDisplay(interesse.valor_maximo)}`
                          : 'Sem faixa de valor definida'}
                      </InteresseSubtext>
                    </InteresseInfo>
                    <DeleteInteresseButton type="button" onClick={() => handleRemoveInteresseImovel(index)}>
                      <DeleteIcon size={16} />
                    </DeleteInteresseButton>
                  </InteresseItem>
                ))}
              </InteresseList>
            ) : (
              <EmptyInteresses>
                Nenhum interesse cadastrado. Adicione interesses para ativar o matching bilateral.
              </EmptyInteresses>
            )}
          </InteresseSection>
        </>
      ) : (
        <>
          <FormRow>
            <FormField>
              <Label>Tipo de Automóvel</Label>
              <SelectWithAdd
                type="tipo_automovel"
                value={tipoAutomovel}
                onChange={(value) => setTipoAutomovel(value)}
                required
              />
            </FormField>
            <FormField>
              <Label>Marca</Label>
              <Input
                type="text"
                value={marca}
                onChange={(e) => setMarca(e.target.value)}
              />
            </FormField>
          </FormRow>
          <FormRow>
            <FormField>
              <Label>Modelo</Label>
              <Input
                type="text"
                value={modelo}
                onChange={(e) => setModelo(e.target.value)}
              />
            </FormField>
            <FormField>
              <Label>Motor</Label>
              <Select value={motor} onChange={(e) => setMotor(e.target.value)}>
                <option value="">Selecione...</option>
                <option value="1.0">1.0</option>
                <option value="1.4">1.4</option>
                <option value="1.6">1.6</option>
                <option value="1.8">1.8</option>
                <option value="2.0">2.0</option>
              </Select>
            </FormField>
          </FormRow>
          <FormField>
            <Label>Valor</Label>
            <Input
              type="number"
              value={valorAutomovel}
              onChange={(e) => setValorAutomovel(e.target.value)}
              required
            />
          </FormField>

          <InteresseSection>
            <InteresseSectionHeader>
              <InteresseSectionTitle>O que aceita em troca?</InteresseSectionTitle>
              <AddInteresseButton type="button" onClick={() => setInteresseModalOpen(true)}>
                + Adicionar Interesse
              </AddInteresseButton>
            </InteresseSectionHeader>
            {interessesAutomovel.length > 0 ? (
              <InteresseList>
                {interessesAutomovel.map((interesse, index) => (
                  <InteresseItem key={index}>
                    <InteresseInfo>
                      <InteresseText>
                        {interesse.tipo_imovel ? `Tipo: ${interesse.tipo_imovel_nome || interesse.tipo_imovel}` : 'Qualquer tipo'}
                        {interesse.zona ? ` | Zona: ${interesse.zona_nome || interesse.zona}` : ''}
                        {interesse.estado ? ` | ${interesse.estado}` : ''}
                      </InteresseText>
                      <InteresseSubtext>
                        {interesse.valor_minimo || interesse.valor_maximo
                          ? `${formatCurrencyDisplay(interesse.valor_minimo)} - ${formatCurrencyDisplay(interesse.valor_maximo)}`
                          : 'Sem faixa de valor definida'}
                      </InteresseSubtext>
                    </InteresseInfo>
                    <DeleteInteresseButton type="button" onClick={() => handleRemoveInteresseAutomovel(index)}>
                      <DeleteIcon size={16} />
                    </DeleteInteresseButton>
                  </InteresseItem>
                ))}
              </InteresseList>
            ) : (
              <EmptyInteresses>
                Nenhum interesse cadastrado. Adicione interesses para ativar o matching bilateral.
              </EmptyInteresses>
            )}
          </InteresseSection>
        </>
      )}

      <Button type="submit" disabled={loading}>
        {loading ? 'Cadastrando...' : 'Cadastrar Permuta'}
      </Button>
    </Form>

    <Modal
      isOpen={proprietarioModalOpen}
      onClose={() => setProprietarioModalOpen(false)}
      title="Novo Proprietário"
    >
      <ProprietarioForm
        onSuccess={(newProprietario) => {
          setProprietario(String(newProprietario.id))
          setProprietarioModalOpen(false)
        }}
        onClose={() => setProprietarioModalOpen(false)}
      />
    </Modal>

    <Modal
      isOpen={interesseModalOpen}
      onClose={() => setInteresseModalOpen(false)}
      title="Adicionar Interesse"
    >
      {tipoPermuta === 'imovel' ? (
        <InteressePermutaImovelForm
          onAdd={handleAddInteresseImovel}
          onClose={() => setInteresseModalOpen(false)}
        />
      ) : (
        <InteressePermutaAutomovelForm
          onAdd={handleAddInteresseAutomovel}
          onClose={() => setInteresseModalOpen(false)}
        />
      )}
    </Modal>
    </>
  )
}

export default PermutaForm
