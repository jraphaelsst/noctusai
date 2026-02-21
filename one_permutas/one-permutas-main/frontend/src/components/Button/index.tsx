import { MouseEventHandler } from 'react'
import { ButtonContainer } from './styles'

type Props = {
  id?: string
  type?: 'button' | 'submit'
  children: string | JSX.Element
  onClick?: MouseEventHandler
}

const Button = ({ id, type, children, onClick }: Props) => {
  return (
    <ButtonContainer id={id} type={type} onClick={onClick}>
      {children}
    </ButtonContainer>
  )
}

export default Button
