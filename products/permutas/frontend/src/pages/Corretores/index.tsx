import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import swal from 'sweetalert2'
import Container from '../../containers/Container'
import Modal from '../../components/Modal'
import CorretorEditForm from '../../components/ModalForms/CorretorEditForm'
import DataTable, { Column } from '../../components/DataTable'
import Button from '../../components/Button'
import useAxios from '../../utils/useAxios'

export type CorretorType = {
  id: number
  nome: string
  telefone: string
  email: string
  creci: string
}

const Corretores = () => {
  const [corretores, setCorretores] = useState<CorretorType[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCorretor, setEditingCorretor] = useState<CorretorType | null>(null)
  const [serverFilters, setServerFilters] = useState<Record<string, string>>({})
  const navigate = useNavigate()
  const api = useAxios()
  const filtersRef = useRef(serverFilters)
  filtersRef.current = serverFilters

  const fetchCorretores = useCallback(async (filters: Record<string, string> = {}) => {
    setIsLoading(true)
    try {
      const params = new URLSearchParams()
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value)
      })
      const queryString = params.toString()
      const url = queryString ? `/corretor/?${queryString}` : '/corretor/'
      const response = await api.get(url)
      setCorretores(Array.isArray(response.data) ? response.data : [])
    } catch (error) {
      console.error('Error fetching corretores:', error)
      setCorretores([])
    } finally {
      setIsLoading(false)
    }
  }, [api])

  useEffect(() => {
    fetchCorretores(filtersRef.current)
  }, [])

  const handleServerFilter = useCallback((filters: Record<string, string>) => {
    setServerFilters(filters)
    fetchCorretores(filters)
  }, [fetchCorretores])

  const columns: Column<CorretorType>[] = [
    { key: 'nome', label: 'Nome', filterable: true, filterKey: 'nome' },
    { key: 'telefone', label: 'Telefone', filterable: true, filterKey: 'telefone' },
    { key: 'email', label: 'Email', filterable: true, filterKey: 'email' },
    { key: 'creci', label: 'CRECI', filterable: true, filterKey: 'creci' },
  ]

  const handleView = (corretor: CorretorType) => {
    navigate(`/corretor/${corretor.id}`)
  }

  const handleDelete = async (corretor: CorretorType) => {
    try {
      await api.delete(`/corretor/${corretor.id}/`)
      swal.fire('Sucesso', 'Corretor excluído com sucesso!', 'success')
      fetchCorretores(serverFilters)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível excluir o corretor.', 'error')
    }
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setEditingCorretor(null)
  }

  return (
    <Container title="Corretores">
      <Button type="button" onClick={() => setIsModalOpen(true)}>
        Cadastrar Novo
      </Button>

      <DataTable
        data={corretores || []}
        columns={columns}
        onView={handleView}
        onEdit={(corretor) => {
          setEditingCorretor(corretor)
          setIsModalOpen(true)
        }}
        onDelete={handleDelete}
        deleteConfirmMessage="Tem certeza que deseja excluir este corretor?"
        loading={isLoading}
        serverFiltering={true}
        onServerFilter={handleServerFilter}
        totalCount={corretores.length}
      />

      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingCorretor ? 'Editar Corretor' : 'Novo Corretor'}
      >
        <CorretorEditForm
          onSuccess={() => {
            fetchCorretores(serverFilters)
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={editingCorretor}
        />
      </Modal>
    </Container>
  )
}

export default Corretores
