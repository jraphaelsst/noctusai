import { useParams, useNavigate } from 'react-router-dom'
import { useState, useEffect } from 'react'
import swal from 'sweetalert2'

import {
  Container,
  Banner,
  Avatar,
  Infos,
  Nome,
  InfoItem,
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
import ClienteForm from '../../../components/ModalForms/ClienteForm'

type ClienteType = {
  id: number
  criado_por: string
  criado_por_nome: string
  corretor: number | null
  corretor_nome: string | null
  nome: string
  telefone: string
  email: string
}

const Cliente = () => {
  const { id } = useParams()
  const navigate = useNavigate()
  const api = useAxios()

  const [cliente, setCliente] = useState<ClienteType | null>(null)
  const [loading, setLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)

  const fetchData = async () => {
    setLoading(true)
    try {
      const response = await api.get(`/proprietario/${id}/`)
      setCliente(response.data)
    } catch (error) {
      console.error('Error fetching cliente:', error)
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
      text: 'Tem certeza que deseja excluir este cliente? Esta ação não pode ser desfeita.',
      icon: 'warning',
      showCancelButton: true,
      confirmButtonColor: '#dc2626',
      cancelButtonColor: '#6b7280',
      confirmButtonText: 'Sim, excluir',
      cancelButtonText: 'Cancelar'
    })

    if (result.isConfirmed) {
      try {
        await api.delete(`/proprietario/${id}/`)
        swal.fire('Excluído!', 'O cliente foi excluído com sucesso.', 'success')
        navigate('/clientes')
      } catch (error) {
        swal.fire('Erro', 'Não foi possível excluir o cliente.', 'error')
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

  if (!cliente) {
    return (
      <Container>
        <Banner>
          <p style={{ color: 'white' }}>Cliente não encontrado</p>
        </Banner>
      </Container>
    )
  }

  const getInitials = (name: string) => {
    return name.split(' ').map(n => n[0]).slice(0, 2).join('').toUpperCase()
  }

  return (
    <Container>
      <Banner>
        <Avatar>{getInitials(cliente.nome)}</Avatar>
        <Infos>
          <Nome>{cliente.nome}</Nome>
          <InfoItem>
            <strong>Telefone:</strong> {cliente.telefone}
          </InfoItem>
          <InfoItem>
            <strong>Email:</strong> {cliente.email}
          </InfoItem>
          <InfoItem>
            <strong>Corretor:</strong> {cliente.corretor_nome || '-'}
          </InfoItem>
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
        title="Editar Cliente"
      >
        <ClienteForm
          onSuccess={() => {
            fetchData()
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={cliente}
        />
      </Modal>

      <Sections>
        <TituloSecao>Informações do Cliente</TituloSecao>
        <Card>
          <InfoItem>
            <strong>ID:</strong> {cliente.id}
          </InfoItem>
          <InfoItem>
            <strong>Nome Completo:</strong> {cliente.nome}
          </InfoItem>
          <InfoItem>
            <strong>Telefone:</strong> {cliente.telefone}
          </InfoItem>
          <InfoItem>
            <strong>Email:</strong> {cliente.email}
          </InfoItem>
          <InfoItem>
            <strong>Corretor Responsável:</strong> {cliente.corretor_nome || '-'}
          </InfoItem>
          <InfoItem>
            <strong>Criado por:</strong> {cliente.criado_por_nome || '-'}
          </InfoItem>
        </Card>
      </Sections>
    </Container>
  )
}

export default Cliente
