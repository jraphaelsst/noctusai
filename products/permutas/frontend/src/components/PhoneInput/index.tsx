import { useState, useEffect } from 'react'
import styled from 'styled-components'
import { color, radius, spacing } from '../../styles'

const Input = styled.input`
  padding: ${spacing.sm} ${spacing.md};
  border: 1px solid ${color.border};
  border-radius: ${radius.md};
  font-size: 14px;
  transition: border-color 0.2s ease;
  width: 100%;
  box-sizing: border-box;

  &:focus {
    outline: none;
    border-color: ${color.primary};
  }
`

type Props = {
  value: string
  onChange: (value: string) => void
  placeholder?: string
  required?: boolean
}

const formatPhone = (value: string): string => {
  const numbers = value.replace(/\D/g, '')
  
  if (numbers.length <= 2) {
    return numbers
  }
  
  if (numbers.length <= 6) {
    return `(${numbers.slice(0, 2)}) ${numbers.slice(2)}`
  }
  
  if (numbers.length <= 10) {
    return `(${numbers.slice(0, 2)}) ${numbers.slice(2, 6)}-${numbers.slice(6)}`
  }
  
  if (numbers.length <= 11) {
    return `(${numbers.slice(0, 2)}) ${numbers.slice(2, 7)}-${numbers.slice(7)}`
  }
  
  if (numbers.length <= 13) {
    return `+${numbers.slice(0, 2)} (${numbers.slice(2, 4)}) ${numbers.slice(4, 9)}-${numbers.slice(9)}`
  }
  
  return `+${numbers.slice(0, 2)} (${numbers.slice(2, 4)}) ${numbers.slice(4, 9)}-${numbers.slice(9, 13)}`
}

const PhoneInput = ({ value, onChange, placeholder = '(11) 99999-9999', required = false }: Props) => {
  const [displayValue, setDisplayValue] = useState('')

  useEffect(() => {
    setDisplayValue(formatPhone(value))
  }, [value])

  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const rawValue = e.target.value
    const formatted = formatPhone(rawValue)
    setDisplayValue(formatted)
    onChange(rawValue.replace(/\D/g, ''))
  }

  return (
    <Input
      type="tel"
      value={displayValue}
      onChange={handleChange}
      placeholder={placeholder}
      required={required}
    />
  )
}

export default PhoneInput
