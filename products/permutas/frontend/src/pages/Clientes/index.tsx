import { useState, useEffect, useCallback, useRef } from 'react'
import { useNavigate } from 'react-router-dom'
import swal from 'sweetalert2'
import Container from '../../containers/Container'
import Modal from '../../components/Modal'
import ClienteForm from '../../components/ModalForms/ClienteForm'
import DataTable, { Column } from '../../components/DataTable'
import Button from '../../components/Button'
import Pagination from '../../components/Pagination'
import useAxios from '../../utils/useAxios'

export type ClienteType = {
  id: number
  criado_por: string
  corretor: number | null
  corretor_nome: string | null
  nome: string
  telefone: string
  email: string
}

type PaginatedResponse<T> = {
  count: number
  next: string | null
  previous: string | null
  results: T[]
}

const Clientes = () => {
  const [clientes, setClientes] = useState<ClienteType[]>([])
  const [isLoading, setIsLoading] = useState(true)
  const [isModalOpen, setIsModalOpen] = useState(false)
  const [editingCliente, setEditingCliente] = useState<ClienteType | null>(null)
  const [currentPage, setCurrentPage] = useState(1)
  const [totalCount, setTotalCount] = useState(0)
  const [totalPages, setTotalPages] = useState(1)
  const [serverFilters, setServerFilters] = useState<Record<string, string>>({})
  const navigate = useNavigate()
  const api = useAxios()
  const filtersRef = useRef(serverFilters)
  filtersRef.current = serverFilters

  const fetchClientes = useCallback(async (page: number = 1, filters: Record<string, string> = {}) => {
    setIsLoading(true)
    try {
      const params = new URLSearchParams()
      params.append('page', String(page))
      Object.entries(filters).forEach(([key, value]) => {
        if (value) params.append(key, value)
      })
      const response = await api.get(`/proprietario/?${params.toString()}`)
      const data = response.data as PaginatedResponse<ClienteType>
      if (data.results) {
        if (data.results.length === 0 && page > 1) {
          setCurrentPage(page - 1)
          return
        }
        setClientes(data.results)
        setTotalCount(data.count)
        setTotalPages(Math.ceil(data.count / 10) || 1)
      } else {
        setClientes(Array.isArray(response.data) ? response.data : [])
      }
    } catch (error: any) {
      if (error?.response?.status === 404 && page > 1) {
        setCurrentPage(page - 1)
        return
      }
      console.error('Error fetching clientes:', error)
      setClientes([])
    } finally {
      setIsLoading(false)
    }
  }, [api])

  useEffect(() => {
    fetchClientes(currentPage, filtersRef.current)
  }, [currentPage])

  const handleServerFilter = useCallback((filters: Record<string, string>) => {
    setServerFilters(filters)
    setCurrentPage(1)
    fetchClientes(1, filters)
  }, [fetchClientes])

  const columns: Column<ClienteType>[] = [
    { key: 'nome', label: 'Nome', filterable: true, filterKey: 'nome' },
    { key: 'telefone', label: 'Telefone', filterable: true, filterKey: 'telefone' },
    { key: 'email', label: 'Email', filterable: true, filterKey: 'email' },
    { 
      key: 'corretor', 
      label: 'Corretor', 
      filterable: true, 
      filterKey: 'corretor',
      render: (item) => item.corretor_nome || '-'
    },
  ]

  const handleView = (cliente: ClienteType) => {
    navigate(`/cliente/${cliente.id}`)
  }

  const handleDelete = async (cliente: ClienteType) => {
    try {
      await api.delete(`/proprietario/${cliente.id}/`)
      swal.fire('Sucesso', 'Cliente excluído com sucesso!', 'success')
      fetchClientes(currentPage, serverFilters)
    } catch (error) {
      swal.fire('Erro', 'Não foi possível excluir o cliente.', 'error')
    }
  }

  const handleCloseModal = () => {
    setIsModalOpen(false)
    setEditingCliente(null)
  }

  return (
    <Container title="Clientes">
      <Button type="button" onClick={() => setIsModalOpen(true)}>
        Cadastrar Novo
      </Button>

      <DataTable
        data={clientes || []}
        columns={columns}
        onView={handleView}
        onEdit={(cliente) => {
          setEditingCliente(cliente)
          setIsModalOpen(true)
        }}
        onDelete={handleDelete}
        deleteConfirmMessage="Tem certeza que deseja excluir este cliente?"
        loading={isLoading}
        serverFiltering={true}
        onServerFilter={handleServerFilter}
        totalCount={totalCount}
      />

      <Pagination
        currentPage={currentPage}
        totalPages={totalPages}
        totalCount={totalCount}
        onPageChange={setCurrentPage}
      />

      <Modal
        isOpen={isModalOpen}
        onClose={handleCloseModal}
        title={editingCliente ? 'Editar Cliente' : 'Novo Cliente'}
      >
        <ClienteForm
          onSuccess={() => {
            fetchClientes(currentPage, serverFilters)
            handleCloseModal()
          }}
          onClose={handleCloseModal}
          initialData={editingCliente}
        />
      </Modal>
    </Container>
  )
}

export default Clientes
