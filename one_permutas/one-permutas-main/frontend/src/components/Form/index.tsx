import { FormEventHandler } from 'react'
import { FormContainer, Title } from './styles'

type Props = {
  title: string
  onSubmit: FormEventHandler<HTMLFormElement>
  children: JSX.Element
}

const Form = ({ title, children, onSubmit }: Props) => {
  return (
    <FormContainer onSubmit={onSubmit}>
      <Title>{title}</Title>
      {children}
    </FormContainer>
  )
}

export default Form
