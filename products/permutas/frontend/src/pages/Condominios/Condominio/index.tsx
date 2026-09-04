import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import swal from 'sweetalert2'

import {
  Container,
  Banner,
  Icon,
  Infos,
  Nome,
  InfoItem,
  Valor,
  Sections,
  TituloSecao,
  Card,
  ActionButtons,
  ActionButton
} from './styles'

import useAxios from '../../../utils/useAxios'
import { LoadingScreen } from '../../../components/Spinner'
import { EditIcon, DeleteIcon } from '../../../components/Icons'
import Modal from '../../../components/Modal'
import CondominioForm from '../../../components/ModalForms/CondominioForm'

type CondominioType = {
  id: number
  criado_por: string
  criado_por_nome: string
  nome: string
  cep: string
  estado: string
  cidade: string
  bairro: string
  endereco: string
  numero: number
  km: number
  valor_condominio: number
}

const Condominio = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useAxios()

  const [condominio, setCondominio] = useState<CondominioType | null>(null)
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const fetchData = async () => {
    setLoading(true)
    try {
      const response = await api.get(`/condominio/${id}/`)
      setCondominio(response.data)
    } catch (error) {
      console.error('Error fetching condominio:', error)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => {
    if (id) {
      fetchData()
    }
  }, [id])

  const handleEdit = () => {
    setIsModalOpen(true)
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
  }

  const handleDelete = async () => {
    const result = await swal.fire({
      title: 'Confirmar exclusão',
      text: 'Tem certeza que deseja excluir este condomínio? Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/condominio/${id}/`)
        swal.fire('Excluído!', 'O condomínio foi excluído com sucesso.', 'success')
        navigate('/condominios')
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o condomínio.', 'error')
      }
    }
  }

  if (loading) {
    return (
      <Container>
        <LoadingScreen />
      </Container>
    )
  }

  if (!condominio) {
    return (
      <Container>
        <Banner>
          <p style={{ color: 'white' }}>Condomínio não encontrado</p>
        </Banner>
      </Container>
    )
  }

  const formatCurrency = (value: number) => {
    return new Intl.NumberFormat('pt-BR', {
      style: 'currency',
      currency: 'BRL'
    }).format(value)
  }

  return (
    <Container>
      <Banner>
        <Icon>🏢</Icon>
        <Infos>
          <Nome>{condominio.nome}</Nome>
          <InfoItem>
            <strong>Endereço:</strong> {condominio.endereco}, {condominio.numero}
          </InfoItem>
          <InfoItem>
            <strong>Bairro:</strong> {condominio.bairro}
          </InfoItem>
          <InfoItem>
            <strong>Cidade:</strong> {condominio.cidade} - {condominio.estado}
          </InfoItem>
          <Valor>Taxa: {formatCurrency(condominio.valor_condominio)}</Valor>
          <ActionButtons>
            <ActionButton onClick={handleEdit} title="Editar">
              <EditIcon size={18} />
            </ActionButton>
            <ActionButton $variant="delete" onClick={handleDelete} title="Excluir">
              <DeleteIcon size={18} />
            </ActionButton>
          </ActionButtons>
        </Infos>
      </Banner>

      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title="Editar Condomínio"
      >
        <CondominioForm
          onSuccess={() => {
            fetchData()
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={condominio}
        />
      </Modal>

      <Sections>
        <TituloSecao>Informações do Condomínio</TituloSecao>
        <Card>
          <InfoItem>
            <strong>ID:</strong> {condominio.id}
          </InfoItem>
          <InfoItem>
            <strong>Nome:</strong> {condominio.nome}
          </InfoItem>
          <InfoItem>
            <strong>CEP:</strong> {condominio.cep}
          </InfoItem>
          <InfoItem>
            <strong>Endereço:</strong> {condominio.endereco}, {condominio.numero}
          </InfoItem>
          <InfoItem>
            <strong>Bairro:</strong> {condominio.bairro}
          </InfoItem>
          <InfoItem>
            <strong>Cidade:</strong> {condominio.cidade}
          </InfoItem>
          <InfoItem>
            <strong>Estado:</strong> {condominio.estado}
          </InfoItem>
          <InfoItem>
            <strong>KM:</strong> {condominio.km}
          </InfoItem>
          <InfoItem>
            <strong>Valor do Condomínio:</strong> {formatCurrency(condominio.valor_condominio)}
          </InfoItem>
          <InfoItem>
            <strong>Criado por:</strong> {condominio.criado_por_nome || '-'}
          </InfoItem>
        </Card>
      </Sections>
    </Container>
  )
}

export default Condominio
