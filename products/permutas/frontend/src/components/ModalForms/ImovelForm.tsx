import { useState, useContext, useEffect } from 'react'
import styled from 'styled-components'
import { jwtDecode } from 'jwt-decode'
import swal from 'sweetalert2'
import useAxios from '../../utils/useAxios'
import { formatCurrency } from '../../utils/formatCurrency'
import { color, radius, spacing } from '../../styles'
import AuthContext from '../../context/AuthContext'
import Modal from '../Modal'
import InteresseImovelForm, { InteresseImovelData } from './InteresseImovelForm'
import InteresseAutomovelForm, { InteresseAutomovelData } from './InteresseAutomovelForm'
import ProprietarioAutocomplete from '../ProprietarioAutocomplete'
import CondominioAutocomplete from '../CondominioAutocomplete'
import CorretorAutocomplete from '../CorretorAutocomplete'
import ProprietarioForm from './ProprietarioForm'
import CondominioQuickForm from './CondominioQuickForm'
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

  &:disabled {
    background: ${color.textMuted};
    cursor: not-allowed;
  }
`

const SecondaryButton = styled.button`
  padding: ${spacing.sm} ${spacing.md};
  background: transparent;
  color: ${color.primary};
  border: 2px solid ${color.primary};
  border-radius: ${radius.md};
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s ease;

  &:hover {
    background: ${color.primary};
    color: ${color.textInverse};
  }
`

const SectionTitle = styled.h3`
  font-size: 16px;
  font-weight: 600;
  color: ${color.text};
  margin: ${spacing.md} 0 ${spacing.sm} 0;
  border-bottom: 1px solid ${color.border};
  padding-bottom: ${spacing.sm};
`

const InteressesList = styled.div`
  display: flex;
  flex-direction: column;
  gap: ${spacing.sm};
  margin-bottom: ${spacing.sm};
`

const InteresseItem = styled.div`
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: ${spacing.sm} ${spacing.md};
  background: ${color.background};
  border-radius: ${radius.sm};
  border: 1px solid ${color.border};
`

const InteresseInfo = styled.span`
  font-size: 14px;
  color: ${color.text};
`

const RemoveButton = styled.button`
  background: none;
  border: none;
  color: #dc2626;
  cursor: pointer;
  font-size: 18px;
  padding: 0 ${spacing.xs};

  &:hover {
    color: #b91c1c;
  }
`

export type ImovelInitialData = {
  id: number
  ref: string
  corretor: string
  tipo: number | null
  tipo_nome?: string | null
  zona: number | null
  zona_nome?: string | null
  valor_venda: number
  proprietario_nome?: string
  condominio_nome?: string
}

type Props = {
  onSuccess: () => void
  onClose: () => void
  initialData?: ImovelInitialData | null
}

import {
  ZONA_LABELS as zonaLabels,
  TIPO_IMOVEL_LABELS as tipoImovelLabels,
  TIPO_AUTOMOVEL_LABELS as tipoAutomovelLabels
} from '../../utils/typeLabels'

const ImovelForm = ({ onSuccess, onClose, initialData }: Props) => {
  const api = useAxios()
  const { authTokens } = useContext(AuthContext)
  
  let user_id = ''
  if (authTokens?.access) {
    const decoded: { user_id: string } = jwtDecode(authTokens.access)
    user_id = decoded.user_id
  }

  const [loading, setLoading] = useState(false)
  const isEditing = !!initialData
  const [editingId, setEditingId] = useState<number | null>(null)

  const [ref, setRef] = useState('')
  const [corretor, setCorretor] = useState('')
  const [proprietario, setProprietario] = useState('')
  const [tipo, setTipo] = useState('')
  const [zona, setZona] = useState('')
  const [condominio, setCondominio] = useState('')
  const [valor, setValor] = useState('')

  const [interessesImoveis, setInteressesImoveis] = useState<InteresseImovelData[]>([])
  const [interessesAutomoveis, setInteressesAutomoveis] = useState<InteresseAutomovelData[]>([])
  
  const [showInteresseImovelModal, setShowInteresseImovelModal] = useState(false)
  const [showInteresseAutomovelModal, setShowInteresseAutomovelModal] = useState(false)
  const [showProprietarioModal, setShowProprietarioModal] = useState(false)

  useEffect(() => {
    if (initialData) {
      setEditingId(initialData.id)
      setRef(initialData.ref || '')
      setCorretor(initialData.corretor || '')
      setTipo(initialData.tipo?.toString() || '')
      setZona(initialData.zona?.toString() || '')
      setValor(initialData.valor_venda?.toString() || '')
    } else {
      setEditingId(null)
      setRef('')
      setCorretor('')
      setProprietario('')
      setTipo('')
      setZona('')
      setCondominio('')
      setValor('')
      setInteressesImoveis([])
      setInteressesAutomoveis([])
    }
  }, [initialData])
  const [showCondominioModal, setShowCondominioModal] = useState(false)

  const handleAddInteresseImovel = (data: InteresseImovelData) => {
    setInteressesImoveis([...interessesImoveis, data])
  }

  const handleRemoveInteresseImovel = (index: number) => {
    setInteressesImoveis(interessesImoveis.filter((_, i) => i !== index))
  }

  const handleAddInteresseAutomovel = (data: InteresseAutomovelData) => {
    setInteressesAutomoveis([...interessesAutomoveis, data])
  }

  const handleRemoveInteresseAutomovel = (index: number) => {
    setInteressesAutomoveis(interessesAutomoveis.filter((_, i) => i !== index))
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
      if (isEditing && editingId) {
        await api.patch(`/imovel/${editingId}/`, {
          ref,
          corretor: corretor ? Number(corretor) : null,
          tipo: tipo || null,
          zona: zona || null,
          valor_venda: Number(valor)
        })

        swal.fire({
          title: 'Imóvel atualizado!',
          icon: 'success',
          toast: true,
          timer: 3000,
          position: 'top-right',
          timerProgressBar: true,
          showConfirmButton: false
        })
      } else {
        const imovelRes = await api.post('/imovel/', {
          criado_por: user_id,
          ref,
          corretor: corretor ? Number(corretor) : null,
          proprietario: Number(proprietario),
          tipo: tipo || null,
          zona: zona || null,
          condominio: Number(condominio),
          valor_venda: Number(valor)
        })

        const imovelId = imovelRes.data.id

        const interesseImovelPromises = interessesImoveis.map(interesse => 
          api.post('/imovel/interesse/imovel/', {
            imovel: imovelId,
            criado_por: user_id,
            tipo_imovel: interesse.tipo_imovel || '',
            estado: interesse.estado || '',
            zona: interesse.zona || '',
            valor_minimo: interesse.valor_minimo ? Number(interesse.valor_minimo) : null,
            valor_maximo: interesse.valor_maximo ? Number(interesse.valor_maximo) : null,
            observacoes: interesse.observacoes || ''
          })
        )

        const interesseAutomovelPromises = interessesAutomoveis.map(interesse => 
          api.post('/imovel/interesse/automovel/', {
            imovel: imovelId,
            criado_por: user_id,
            tipo_automovel: interesse.tipo_automovel || '',
            valor_minimo: interesse.valor_minimo ? Number(interesse.valor_minimo) : null,
            valor_maximo: interesse.valor_maximo ? Number(interesse.valor_maximo) : null
          })
        )

        await Promise.all([...interesseImovelPromises, ...interesseAutomovelPromises])

        swal.fire({
          title: 'Imóvel cadastrado!',
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
    } catch (err) {
      console.error('Error creating imovel:', err)
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
        <FormRow>
          <FormField>
            <Label>Referência</Label>
            <Input
              type="text"
              value={ref}
              onChange={(e) => setRef(e.target.value)}
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

        <FormRow>
          <FormField>
            <Label>Proprietário</Label>
            <ProprietarioAutocomplete
              value={proprietario}
              onChange={(id) => setProprietario(id)}
              onAddClick={() => setShowProprietarioModal(true)}
              required
            />
          </FormField>
          <FormField>
            <Label>Condomínio</Label>
            <CondominioAutocomplete
              value={condominio}
              onChange={(id) => setCondominio(id)}
              onAddClick={() => setShowCondominioModal(true)}
              required
            />
          </FormField>
        </FormRow>

        <FormRow>
          <FormField>
            <Label>Tipo</Label>
            <SelectWithAdd
              type="tipo_imovel"
              value={tipo}
              onChange={(value) => setTipo(value)}
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
            <Label>Valor de Venda</Label>
            <Input
              type="number"
              value={valor}
              onChange={(e) => setValor(e.target.value)}
              required
            />
          </FormField>
          <FormField />
        </FormRow>

        <SectionTitle>Interesses Imobiliários</SectionTitle>
        {interessesImoveis.length > 0 && (
          <InteressesList>
            {interessesImoveis.map((interesse, index) => (
              <InteresseItem key={index}>
                <InteresseInfo>
                  {interesse.tipo_imovel ? tipoImovelLabels[interesse.tipo_imovel] : 'Todos os tipos'}
                  {interesse.zona ? ` - ${zonaLabels[interesse.zona]}` : ' - Todas as zonas'}
                  {interesse.estado && ` - ${interesse.estado}`}
                  {interesse.valor_minimo && ` - Min: ${formatCurrency(Number(interesse.valor_minimo))}`}
                  {interesse.valor_maximo && ` - Max: ${formatCurrency(Number(interesse.valor_maximo))}`}
                </InteresseInfo>
                <RemoveButton type="button" onClick={() => handleRemoveInteresseImovel(index)}>
                  ×
                </RemoveButton>
              </InteresseItem>
            ))}
          </InteressesList>
        )}
        <SecondaryButton type="button" onClick={() => setShowInteresseImovelModal(true)}>
          + Adicionar Interesse Imobiliário
        </SecondaryButton>

        <SectionTitle>Interesses de Automóveis</SectionTitle>
        {interessesAutomoveis.length > 0 && (
          <InteressesList>
            {interessesAutomoveis.map((interesse, index) => (
              <InteresseItem key={index}>
                <InteresseInfo>
                  {interesse.tipo_automovel ? tipoAutomovelLabels[interesse.tipo_automovel] : 'Todos os tipos'}
                  {interesse.valor_minimo && ` - Min: ${formatCurrency(Number(interesse.valor_minimo))}`}
                  {interesse.valor_maximo && ` - Max: ${formatCurrency(Number(interesse.valor_maximo))}`}
                </InteresseInfo>
                <RemoveButton type="button" onClick={() => handleRemoveInteresseAutomovel(index)}>
                  ×
                </RemoveButton>
              </InteresseItem>
            ))}
          </InteressesList>
        )}
        <SecondaryButton type="button" onClick={() => setShowInteresseAutomovelModal(true)}>
          + Adicionar Interesse de Automóvel
        </SecondaryButton>

        <Button type="submit" disabled={loading}>
          {loading ? 'Cadastrando...' : 'Cadastrar Imóvel'}
        </Button>
      </Form>

      {showInteresseImovelModal && (
        <Modal
          isOpen={showInteresseImovelModal}
          onClose={() => setShowInteresseImovelModal(false)}
          title="Adicionar Interesse Imobiliário"
        >
          <InteresseImovelForm
            onAdd={handleAddInteresseImovel}
            onClose={() => setShowInteresseImovelModal(false)}
          />
        </Modal>
      )}

      {showInteresseAutomovelModal && (
        <Modal
          isOpen={showInteresseAutomovelModal}
          onClose={() => setShowInteresseAutomovelModal(false)}
          title="Adicionar Interesse de Automóvel"
        >
          <InteresseAutomovelForm
            onAdd={handleAddInteresseAutomovel}
            onClose={() => setShowInteresseAutomovelModal(false)}
          />
        </Modal>
      )}

      {showProprietarioModal && (
        <Modal
          isOpen={showProprietarioModal}
          onClose={() => setShowProprietarioModal(false)}
          title="Novo Proprietário"
        >
          <ProprietarioForm
            onSuccess={(newProprietario) => {
              setProprietario(String(newProprietario.id))
              setShowProprietarioModal(false)
            }}
            onClose={() => setShowProprietarioModal(false)}
          />
        </Modal>
      )}

      {showCondominioModal && (
        <Modal
          isOpen={showCondominioModal}
          onClose={() => setShowCondominioModal(false)}
          title="Novo Condomínio"
        >
          <CondominioQuickForm
            onSuccess={(newCondominio) => {
              setCondominio(String(newCondominio.id))
              setShowCondominioModal(false)
            }}
            onClose={() => setShowCondominioModal(false)}
          />
        </Modal>
      )}

    </>
  )
}

export default ImovelForm
