import { useState } from 'react'
import styled from 'styled-components'
import { color, radius, spacing } from '../../styles'
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
`

export type InteresseAutomovelData = {
  tipo_automovel: string
  valor_minimo: string
  valor_maximo: string
}

type InitialData = {
  tipo_automovel?: number | null
  valor_minimo?: number | null
  valor_maximo?: number | null
}

type Props = {
  onAdd: (data: InteresseAutomovelData) => void
  onClose: () => void
  initialData?: InitialData
}

const InteresseAutomovelForm = ({ onAdd, onClose, initialData }: Props) => {
  const [tipoAutomovel, setTipoAutomovel] = useState(initialData?.tipo_automovel?.toString() || '')
  const [valorMinimo, setValorMinimo] = useState(initialData?.valor_minimo?.toString() || '')
  const [valorMaximo, setValorMaximo] = useState(initialData?.valor_maximo?.toString() || '')

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    onAdd({
      tipo_automovel: tipoAutomovel === 'all' ? '' : tipoAutomovel,
      valor_minimo: valorMinimo,
      valor_maximo: valorMaximo
    })
    onClose()
  }

  return (
    <>
      <Form onSubmit={handleSubmit}>
        <FormRow>
          <FormField>
            <Label>Tipo de Automóvel</Label>
            <SelectWithAdd
              type="tipo_automovel"
              value={tipoAutomovel}
              onChange={(value) => setTipoAutomovel(value)}
              showAllOption
            />
          </FormField>
        </FormRow>

        <FormRow>
          <FormField>
            <Label>Valor Mínimo</Label>
            <Input
              type="number"
              value={valorMinimo}
              onChange={(e) => setValorMinimo(e.target.value)}
              placeholder="Ex: 50000"
            />
          </FormField>
          <FormField>
            <Label>Valor Máximo</Label>
            <Input
              type="number"
              value={valorMaximo}
              onChange={(e) => setValorMaximo(e.target.value)}
              placeholder="Ex: 100000"
            />
          </FormField>
        </FormRow>

        <Button type="submit">Adicionar Interesse de Automóvel</Button>
      </Form>

    </>
  )
}

export default InteresseAutomovelForm
