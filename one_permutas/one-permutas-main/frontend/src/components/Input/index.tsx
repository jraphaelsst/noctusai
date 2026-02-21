import { ChangeEventHandler } from 'react'
import { InputField } from './styles'

type Props = {
  id: string
  type: string
  placeholder: string
  onChange: ChangeEventHandler<HTMLInputElement>
}

const Input = ({ id, type, placeholder, onChange }: Props) => {
  return (
    <InputField
      id={id}
      type={type}
      placeholder={placeholder}
      onChange={onChange}
    />
  )
}

export default Input
